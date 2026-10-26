"""Cliente de datos in-process: plan exacto de consultas → evidencia original.

Es el motor de la skill A2A `execute_plan` del agente de datos
(`a2a_agents/data_server.py`): valida cada operación y sus argumentos, pagina con
cursores, verifica identidad y procedencia de cada respuesta y crea `Evidence`
sin pasar por un LLM. Los tests y scripts locales también lo usan directamente.

La caché vive con la instancia: quien la reutiliza ahorra consultas repetidas y
cuota de la API (120 consultas/min por clave).
"""

import asyncio
import json
import time
from collections import deque
from typing import Protocol

from pydantic import ValidationError

from inside_game.agents.contracts import Evidence
from inside_game.contracts import ApiResponse
from inside_game.service import OPERATIONS

# Códigos conocidos; nunca se reenvían mensajes externos.
KNOWN_ERRORS = {
    "RATE_LIMITED",
    "BUSY",
    "API_UNAVAILABLE",
    "UNAUTHORIZED",
    "FORBIDDEN",
    "NOT_FOUND",
    "MATCH_NOT_FOUND",
    "INVALID_ARGUMENT",
    "RESPONSE_TOO_LARGE",
    "ENTITY_NOT_IN_MATCH",
    "INSUFFICIENT_COVERAGE",
    "SOURCE_FIELD_UNAVAILABLE",
    "WINDOW_TOO_LARGE",
}


# Reanudar la base serverless tarda decenas de segundos: se sondea cada pocos.
COLD_START_POLL_S = 3
COLD_START_POLLS = 25
# La API atiende 4 consultas a la vez por clave; se deja margen a otros clientes.
CONCURRENT_QUERIES = 3


class Transport(Protocol):
    async def call(
        self, operation: str, arguments: dict
    ) -> tuple[dict | None, str | None]:
        """Devuelve (payload, None) o (None, código de error)."""


class HttpTransport:
    """API REST con clave del servidor.

    La API limita a 120 consultas por ventana deslizante de 60 s: se respeta con
    esa misma ventana (un informe de ~40 consultas sale en ráfaga) y no con un
    espaciado fijo, que lo habría multiplicado por 0,6 s por consulta.
    """

    def __init__(self, client, *, min_interval_s=0.0, rate_per_minute=110):
        self.client = client
        self.min_interval_s = min_interval_s
        self.rate_per_minute = rate_per_minute
        self.sent = deque()
        self.last_post = 0.0

    async def _slot(self):
        while True:
            now = time.monotonic()
            while self.sent and self.sent[0] <= now - 60:
                self.sent.popleft()
            wait = self.min_interval_s - (now - self.last_post)
            if len(self.sent) >= self.rate_per_minute:
                wait = max(wait, self.sent[0] + 60 - now)
            if wait <= 0:
                self.sent.append(now)
                self.last_post = now
                return
            await asyncio.sleep(wait)

    async def call(self, operation, arguments):
        limited = resumed = 0
        while True:
            await self._slot()
            response = await self.client.post(
                f"/api/operations/{operation}", json=arguments
            )
            if response.status_code == 200:
                return response.json(), None
            if response.status_code == 429 and limited < 3:
                limited += 1
                await asyncio.sleep(float(response.headers.get("retry-after", "60")))
                continue
            if response.status_code == 503 and resumed < COLD_START_POLLS:
                # La base serverless se pausa: se sondea hasta que despierte, sin
                # esperar tramos largos de más.
                resumed += 1
                await asyncio.sleep(COLD_START_POLL_S)
                continue
            if response.status_code in (429, 503):
                return None, "API_UNAVAILABLE"
            try:
                code = response.json()["error"]["code"]
            except (ValueError, KeyError, TypeError):
                code = f"HTTP_{response.status_code}"
            return (
                None,
                code if code in KNOWN_ERRORS else f"HTTP_{response.status_code}",
            )


class McpTransport:
    """MCP de datos (mismo camino que el agente de datos)."""

    def __init__(self, client):
        self.client = client

    async def call(self, operation, arguments):
        for attempt in range(2):
            result = await self.client.call_tool(operation, arguments)
            if not result.is_error:
                return result.structured_content, None
            try:
                code = json.loads(result.content[0].text)["error"]["code"]
            except (ValueError, KeyError, IndexError, AttributeError, TypeError):
                return None, "INVALID_MCP_RESPONSE"
            if code in {"RATE_LIMITED", "BUSY", "API_UNAVAILABLE"} and attempt == 0:
                await asyncio.sleep(1)
                continue
            return None, code if code in KNOWN_ERRORS else "MCP_TOOL_FAILED"
        return None, "MCP_TOOL_FAILED"


class EvidenceClient:
    def __init__(
        self, transport: Transport, *, max_pages=30, max_bytes=24 * 1024 * 1024
    ):
        self.transport = transport
        self.max_pages = max_pages
        self.max_bytes = max_bytes
        self.evidence: dict[str, dict] = {}
        self.queries: dict[str, tuple[list[str], str | None]] = {}
        self.calls = 0
        self.bytes = 0
        self._started = 0
        self._inflight: dict[str, asyncio.Future] = {}
        self._slots = asyncio.Semaphore(CONCURRENT_QUERIES)

    async def fetch(self, operation, arguments):
        """Interfaz del resolvedor: (páginas de evidencia, error)."""
        ids, error = await self.query(operation, arguments)
        return [self.evidence[i] for i in ids], error

    async def query(self, operation, arguments):
        if operation not in OPERATIONS:
            return [], "UNREGISTERED_OPERATION"
        try:
            checked = (
                OPERATIONS[operation].model_validate(arguments).model_dump(mode="json")
            )
        except ValidationError:
            return [], "INVALID_ARGUMENT"
        key = operation + json.dumps(checked, sort_keys=True)
        if key in self.queries:
            return self.queries[key]
        if key in self._inflight:
            return await self._inflight[key]
        # El ID se asigna antes de esperar nada: es estable con consultas en paralelo.
        self._started += 1
        query_id = f"q{self._started}"
        task = asyncio.ensure_future(self._pages(operation, checked, query_id))
        self._inflight[key] = task
        try:
            self.queries[key] = await task
        finally:
            del self._inflight[key]
        return self.queries[key]

    async def _pages(self, operation, checked, query_id):
        ids, args, cursors = [], checked, set()
        result = None
        for page in range(self.max_pages):
            self.calls += 1
            async with self._slots:
                payload, error = await self.transport.call(operation, args)
            if error:
                # Una página parcial no se presenta como consulta completa.
                result = ([], error)
                break
            try:
                response = ApiResponse.model_validate(payload)
                if (
                    response.operation_id != operation
                    or type(response.provenance.get("is_synthetic")) is not bool
                ):
                    raise ValueError
            except (ValidationError, ValueError):
                result = ([], "INVALID_DATA_RESPONSE")
                break
            evidence = Evidence(
                evidence_id=f"{query_id}-p{page + 1}",
                query_id=query_id,
                operation=operation,
                arguments=args,
                response=response,
            ).model_dump(mode="json")
            self.bytes += len(json.dumps(evidence).encode())
            if self.bytes > self.max_bytes:
                result = ([], "EVIDENCE_BUDGET_EXCEEDED")
                break
            self.evidence[evidence["evidence_id"]] = evidence
            ids.append(evidence["evidence_id"])
            cursor = response.pagination.get("next_cursor")
            if not cursor:
                result = (ids, None)
                break
            if not isinstance(cursor, str) or cursor in cursors:
                result = ([], "INVALID_PAGINATION")
                break
            cursors.add(cursor)
            args = {**checked, "cursor": cursor}
        else:
            result = ([], "PAGE_BUDGET_EXCEEDED")
        return result

    async def run(self, queries):
        """Ejecuta un plan: clave de consulta → (ids de evidencia, error).

        Las consultas independientes van en paralelo; las páginas de una misma
        consulta siguen en orden porque cada cursor depende de la anterior.
        """
        results = await asyncio.gather(
            *(self.query(q.operation, q.arguments) for q in queries)
        )
        return {q.key: result for q, result in zip(queries, results, strict=True)}
