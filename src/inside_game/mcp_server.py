"""Permite que un agente consulte la API mediante herramientas MCP.

Flujo de una petición: tools/call -> ApiBridge -> POST de la API -> Azure SQL.
La API conserva las consultas y los cálculos; este módulo adapta el protocolo,
valida argumentos y devuelve los datos con su procedencia sintética.

Uso desde el entorno virtual, con la API iniciada previamente:
    python -m inside_game.mcp_server
    python -m inside_game.mcp_server --transport streamable-http --port 8001

El primer comando habla por stdin/stdout con el cliente que lo inicia. El segundo
atiende en http://127.0.0.1:8001/mcp. Configuración y ejemplos: docs/mcp.md.
"""

import argparse
import asyncio
import json
import logging
import os
import time
from collections import deque
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import (
    CallToolResult,
    ListToolsResult,
    TextContent,
    Tool,
    ToolAnnotations,
)
from pydantic import ValidationError
from starlette.middleware import Middleware
from starlette.responses import JSONResponse

from inside_game.contracts import ApiResponse
from inside_game.service import OPERATIONS

log = logging.getLogger("inside_game.mcp")
# Límites en bytes. En HTTP, MAX_REQUEST limita todo el cuerpo JSON-RPC;
# en ApiBridge limita los argumentos ya extraídos de la llamada MCP.
MAX_REQUEST = 65536
MAX_RESPONSE = 1024 * 1024
# El cliente recibe estas instrucciones al descubrir el servidor. Orientan la
# interpretación de datos; la validación efectiva ocurre en call() y en la API.
INSTRUCTIONS = (
    "Analítica de fútbol con datos sintéticos. Usa describe_dataset para conocer "
    "cobertura y limitaciones, list_matches/find_entities para resolver identificadores, "
    "y get_match_context para alineaciones. Sólo se permiten las herramientas listadas; "
    "no se acepta SQL. Conserva provenance, warnings, coverage y coordinates al interpretar "
    "resultados. El xG es ilustrativo; Voronoi no es probabilidad de control. El tracking "
    "es de 1 Hz; las ventanas son [start_ms,end_ms) y el tiempo corresponde al período. "
    "Usa pagination.next_cursor con los mismos argumentos para continuar. Si no hay "
    "cobertura, explica la ausencia sin inventar datos."
)
# Descripciones que ve el agente en tools/list para elegir la herramienta.
# Los campos, enums y límites se obtienen de OPERATIONS, no de este texto.
DESCRIPTIONS = {
    "describe_dataset": "Descubre cobertura, convenciones y limitaciones del conjunto sintético.",
    "find_entities": "Resuelve nombres a identificadores de equipos o jugadores; no adivines IDs.",
    "list_matches": "Lista partidos disponibles con filtros y paginación.",
    "get_match_context": "Obtiene contexto, equipos, alineaciones e intervalos de participación del partido.",
    "get_team_summary": "Resume métricas de un equipo en partidos, con un profile_id autorizado.",
    "get_player_summary": "Resume métricas de un jugador y sus minutos con un profile_id autorizado.",
    "get_shots": "Consulta tiros, ubicación, tiempo, resultado y xG ilustrativo; on_target incluye goles y paradas.",
    "get_passes": "Consulta pases, origen, destino, altura, resultados y resumen de completados.",
    "get_defensive_actions": "Consulta entradas, intercepciones, recuperaciones, presiones y duelos aéreos sin duplicar el enfrentamiento.",
    "get_ball_actions": "Consulta regates y conducciones; la distancia de conducción es desplazamiento entre extremos.",
    "get_discipline": "Consulta faltas y disciplina anotadas; un resultado vacío no prueba ausencia de infracciones reales.",
    "get_substitutions": "Consulta cambios y participantes reemplazados del partido.",
    "get_possessions": "Consulta secuencias de posesión anotadas; su tramo de eventos no equivale a posesión temporal exacta.",
    "get_tracking_frame": "Obtiene coordenadas de jugadores y balón en un instante muestreado de un período, a 1 Hz.",
    "get_tracking_window": "Obtiene tracking de una ventana de hasta 120 segundos, con paginación.",
    "get_event_context": "Obtiene contexto de un evento por UUID, capturas disponibles y tracking cercano.",
    "get_heatmap": "Genera celdas de mapa de calor por eventos o segundos de ocupación; conserva unidades y coordenadas.",
    "get_movement_summary": "Resume distancia y movimiento a partir de tracking de 1 Hz e intervalos activos.",
    "get_metric_series": "Genera series temporales de perfiles de eventos autorizados; no acepta fórmulas libres.",
    "compare_entities": "Compara equipos, jugadores o ventanas con métricas y normalizaciones autorizadas.",
    "get_set_piece_sequences": "Consulta secuencias que comienzan en un reinicio como córner o saque de banda.",
    "get_events": "Consulta eventos por tipos y filtros enumerados, sin SQL ni expresiones libres.",
    "get_sequences": "Busca patrones predeterminados: pase A-B-A, tras regate, recuperación a tiro o presión a recuperación.",
    "get_zone_summary": "Resume actividad y ocupación en zonas predefinidas del campo.",
    "get_rankings": "Ordena equipos o jugadores por métricas autorizadas, totales o por 90 minutos.",
    "get_team_shape": "Calcula centroide, anchura, profundidad, distancias y envolvente del equipo; requiere instante o ventana válida.",
    "get_proximity_connectivity": "Calcula grafo de proximidad y conectividad según epsilon_m discreto.",
    "get_space_coverage": "Calcula áreas Voronoi recortadas al campo; geometría, no pitch control probabilístico.",
    "get_passing_network": "Construye red dirigida de pases completados con pesos y jugadores participantes.",
    "get_pass_corridor": "Evalúa un corredor estático 2D de un pase raso anotado; requiere event_id, no predice intercepciones.",
    "get_line_breaks": "Evalúa rupturas de líneas según la definición geométrica publicada y eventos disponibles.",
    "get_persistent_structure": "Calcula persistencia de Vietoris-Rips y Betti en escalas definidas; no es un score táctico calibrado.",
    "get_node_removal_robustness": "Mide cambios de conectividad al retirar nodos del grafo de proximidad.",
    "get_defensive_profile": "Combina forma y conectividad defensiva con contexto de acciones rivales; no produce un score de impenetrabilidad.",
}


@dataclass(frozen=True)
class McpSettings:
    """Destino y credencial de la API, definidos por quien ejecuta el servidor.

    api_url es el origen sin /api; ApiBridge añade la ruta fija de cada consulta.
    api_key se envía como Bearer y nunca como argumento de una herramienta.
    """

    api_url: str = "http://127.0.0.1:8000"
    api_key: str = ""

    def __post_init__(self):
        # Impide incrustar credenciales o parámetros en la URL. Una API remota
        # requiere TLS y clave, aunque el servidor MCP siga siendo local.
        url = urlsplit(self.api_url)
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or url.path not in ("", "/")
        ):
            raise ValueError(
                "MCP API URL must be an HTTP(S) origin without credentials or path"
            )
        local = url.hostname in ("127.0.0.1", "localhost", "::1")
        if not local and (url.scheme != "https" or len(self.api_key) < 32):
            raise ValueError(
                "A remote API requires HTTPS and a bearer key of at least 32 characters"
            )

    @classmethod
    def from_env(cls):
        """Lee el entorno del proceso; start-mcp.ps1 puede cargar .env.local."""
        return cls(
            api_url=os.getenv("INSIDE_GAME_MCP_API_URL", cls.api_url),
            api_key=os.getenv("INSIDE_GAME_API_KEY", ""),
        )


def tool_catalog():
    """Publica una herramienta por operación con sus contratos de entrada/salida.

    Reutilizar los modelos de la API evita que MCP anuncie parámetros distintos.
    Las anotaciones informan al cliente; los permisos reales los impone la API.
    """
    return [
        Tool(
            name=name,
            description=DESCRIPTIONS[name] + " Sólo lectura; datos sintéticos.",
            input_schema=model.model_json_schema(),
            output_schema=ApiResponse.model_json_schema(),
            annotations=ToolAnnotations(
                read_only_hint=True,
                destructive_hint=False,
                idempotent_hint=True,
                open_world_hint=False,
            ),
        )
        for name, model in OPERATIONS.items()
    ]


def failure(code, message, *, fields=None):
    """Construye un error recuperable para que el agente corrija o reintente.

    No devuelve structured_content: el esquema de salida describe éxitos, no
    errores. fields sólo debe incluir ubicación y tipo, nunca valores enviados.
    """
    payload = {"error": {"code": code, "message": message}}
    if fields is not None:
        payload["error"]["fields"] = fields
    return CallToolResult(
        content=[
            TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))
        ],
        is_error=True,
    )


class ApiBridge:
    """Valida llamadas MCP y las traduce a las rutas HTTP predeterminadas.

    transport permite inyectar una API de pruebas sin abrir sockets ni usar
    Azure. En ejecución normal, httpx se conecta al origen de McpSettings.
    Los contadores de concurrencia y frecuencia se comparten por esta instancia.
    """

    def __init__(self, settings=None, transport=None, token_provider=None):
        self.settings = settings or McpSettings.from_env()
        self.transport = transport
        self.token_provider = token_provider
        self.active = 0
        self.requests = deque()

    async def call(self, name, arguments):
        """Recibe nombre + objeto JSON y devuelve un CallToolResult MCP.

        Rechaza herramientas desconocidas y argumentos inválidos antes de hacer
        HTTP. En caso de éxito conserva el objeto de la API; los fallos se
        traducen a errores públicos sin revelar excepciones ni credenciales.
        """
        if name not in OPERATIONS:
            return failure("UNREGISTERED_OPERATION", "Tool is not registered.")
        try:
            raw = json.dumps(arguments, allow_nan=False).encode()
            if len(raw) > MAX_REQUEST:
                return failure("REQUEST_TOO_LARGE", "Arguments are limited to 64 KiB.")
            request = OPERATIONS[name].model_validate(arguments)
        except (ValueError, TypeError) as exc:
            fields = (
                [{"location": list(e["loc"]), "type": e["type"]} for e in exc.errors()]
                if isinstance(exc, ValidationError)
                else None
            )
            return failure(
                "INVALID_ARGUMENT",
                "Arguments do not satisfy the tool contract.",
                fields=fields,
            )
        # Ventana móvil de un minuto, independiente de cambios del reloj del
        # sistema. No hay await entre comprobar el cupo y reservar una llamada.
        now = time.monotonic()
        while self.requests and self.requests[0] < now - 60:
            self.requests.popleft()
        if len(self.requests) >= 120:
            return failure(
                "RATE_LIMITED", "Tool call limit reached. Retry after one minute."
            )
        self.requests.append(now)
        if self.active >= 4:
            return failure("BUSY", "Concurrent tool limit reached. Retry shortly.")
        self.active += 1
        try:
            # Presupuesto total, además del timeout de conexión/lectura HTTP.
            async with asyncio.timeout(35):
                return await self._post(name, request)
        except (httpx.HTTPError, TimeoutError):
            return failure(
                "API_UNAVAILABLE",
                "Analytics API unavailable. Check that it is running and retry.",
            )
        except Exception as exc:  # noqa: BLE001 -- protocol boundary must not leak backend details
            log.error("tool_failed operation=%s type=%s", name, type(exc).__name__)
            return failure("INTERNAL_ERROR", "Tool could not be completed.")
        finally:
            # Libera el cupo también ante timeout, excepción o cancelación.
            self.active -= 1

    async def _post(self, name, request):
        """Envía el modelo validado a la API y comprueba su respuesta.

        name ya pertenece a OPERATIONS y request es su modelo Pydantic. El
        cliente no puede elegir rutas, URLs, cabeceras ni sentencias SQL.
        """
        headers = {}
        key = self.token_provider() if self.token_provider else self.settings.api_key
        if key:
            headers["Authorization"] = "Bearer " + key
        async with httpx.AsyncClient(  # noqa: SIM117 -- keep client and streamed response lifetimes visible
            base_url=self.settings.api_url.rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(32, connect=5),
            follow_redirects=False,
            trust_env=False,
            transport=self.transport,
        ) as client:
            async with client.stream(
                "POST", "/api/operations/" + name, json=request.model_dump(mode="json")
            ) as response:
                if response.status_code != 200:
                    # No reenviar el cuerpo del error upstream: podría contener
                    # detalles internos. Se proporciona un mensaje controlado.
                    code, message = {
                        401: (
                            "UNAUTHORIZED",
                            "API authentication failed. Check server configuration.",
                        ),
                        403: ("FORBIDDEN", "API access denied."),
                        404: (
                            "NOT_FOUND",
                            "Requested resource or operation is unavailable.",
                        ),
                        413: (
                            "RESPONSE_TOO_LARGE",
                            "Select a smaller window or page size.",
                        ),
                        422: (
                            "INVALID_ARGUMENT",
                            "API rejected the arguments. Check the tool contract and dataset coverage.",
                        ),
                        429: (
                            "RATE_LIMITED",
                            "API limit reached. Retry after one minute.",
                        ),
                    }.get(
                        response.status_code,
                        (
                            "API_UNAVAILABLE",
                            "Analytics API could not complete the query. Retry shortly.",
                        ),
                    )
                    return failure(code, message)
                # Leer por bloques permite cortar una respuesta demasiado grande
                # sin confiar en Content-Length ni cargarla entera en memoria.
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE:
                        return failure(
                            "RESPONSE_TOO_LARGE",
                            "Select a smaller window or page size.",
                        )
                    chunks.append(chunk)
        # Exige el contrato de la API, la operación solicitada y la identificación
        # sintética antes de ofrecer el resultado al agente.
        try:
            result = ApiResponse.model_validate_json(b"".join(chunks))
            if (
                result.operation_id != name
                or result.provenance.get("is_synthetic") is not True
            ):
                raise ValueError("Unexpected operation or provenance")
        except ValueError:
            return failure(
                "INVALID_API_RESPONSE",
                "API response does not satisfy the published contract.",
            )
        payload = result.model_dump(mode="json")
        # El objeto estructurado sirve a clientes actuales; el JSON de texto
        # mantiene compatibilidad con clientes que sólo leen content.
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(payload, ensure_ascii=False, allow_nan=False),
                )
            ],
            structured_content=payload,
            is_error=False,
        )


def create_server(
    settings=None,
    transport=None,
    token_provider=None,
    operation_provider=None,
    audit_callback=None,
):
    """Conecta descubrimiento y ejecución MCP con una misma instancia del puente.

    Crear el servidor no consulta Azure. tools/list describe las herramientas;
    tools/call invoca la API únicamente cuando el cliente pide una operación.
    """
    bridge = ApiBridge(settings, transport, token_provider)

    async def list_tools(ctx, params):
        allowed = operation_provider() if operation_provider else OPERATIONS
        return ListToolsResult(
            tools=[tool for tool in tool_catalog() if tool.name in allowed]
        )

    async def call_tool(ctx, params):
        if (
            operation_provider
            and params.name in OPERATIONS
            and params.name not in operation_provider()
        ):
            result = failure(
                "FORBIDDEN", "This credential cannot use the requested operation."
            )
        else:
            result = await bridge.call(
                params.name, params.arguments if params.arguments is not None else {}
            )
        if audit_callback:
            audit_callback(
                params.name if params.name in OPERATIONS else "unregistered",
                result.is_error,
            )
        return result

    return Server(
        "inside-game-analytics",
        version="1.0.0",
        instructions=INSTRUCTIONS,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


async def run_stdio(server):
    """Atiende el protocolo por los streams del proceso iniciado por el cliente."""
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main():
    """Punto de entrada de inside-game-mcp y python -m inside_game.mcp_server."""
    parser = argparse.ArgumentParser(
        description="Inside the game MCP: closed analytics tools"
    )
    parser.add_argument(
        "--transport", choices=("stdio", "streamable-http"), default="stdio"
    )
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")
    # Un print de diagnóstico en stdout rompería el protocolo stdio.
    # logging escribe en stderr; stdout queda reservado a mensajes MCP.
    logging.basicConfig(level=logging.WARNING)
    server = create_server()
    if args.transport == "stdio":
        asyncio.run(run_stdio(server))
    else:
        import uvicorn

        uvicorn.run(
            create_http_app(server),
            host="127.0.0.1",
            port=args.port,
            proxy_headers=False,
            access_log=False,
        )


def create_http_app(server=None):
    """Crea el endpoint /mcp para clientes del mismo equipo.

    Stateless evita conservar sesiones entre solicitudes. Host/Origin protegen
    contra DNS rebinding y LoopbackOnly comprueba la dirección real del cliente.
    Esta configuración no está preparada para publicarse mediante un proxy.
    """
    server = server or create_server()
    app = server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        max_request_body_size=MAX_REQUEST,
        transport_security=TransportSecuritySettings(
            allowed_hosts=["127.0.0.1:*", "localhost:*", "127.0.0.1", "localhost"],
            allowed_origins=["http://127.0.0.1:*", "http://localhost:*"],
        ),
    )
    app.user_middleware.insert(0, Middleware(LoopbackOnly))
    return app


class LoopbackOnly:
    """Middleware ASGI que rechaza HTTP procedente de otros equipos.

    Consulta scope.client, no X-Forwarded-For. Deja pasar los eventos lifespan
    para que el SDK pueda iniciar y cerrar sus recursos normalmente.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and (scope.get("client") or ("",))[0] not in (
            "127.0.0.1",
            "::1",
        ):
            response = JSONResponse({"error": "Local MCP access only"}, status_code=403)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


if __name__ == "__main__":
    main()
