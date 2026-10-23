# MCP de analítica deportiva

Servidor implementado con el [SDK oficial de MCP para Python](https://py.sdk.modelcontextprotocol.io/advanced/low-level-server/). Expone **34 herramientas de sólo lectura**: las mismas 25 consultas de datos y nueve análisis espaciales/topológicos de la [API](api.md). El registro y los modelos Pydantic son compartidos, sin mantener otra implementación de las consultas.

Flujo: **cliente o agente → herramienta MCP → API HTTP → vistas de lectura de Azure SQL**. El MCP no necesita credenciales SQL, no abre conexiones a la base y no ejecuta SQL enviado por el cliente. La API debe estar activa. Todos los resultados identifican su procedencia sintética.

## Arranque

Usa Python 3.12 o superior y el entorno del repositorio. Para instalar o actualizar:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Primero inicia la API en una terminal:

```powershell
.\scripts\start-api.ps1
```

Para conectar desde un cliente MCP por HTTP, inicia en otra terminal:

```powershell
.\scripts\start-mcp.ps1 -Transport streamable-http
```

La dirección del servidor es **http://127.0.0.1:8001/mcp**. Se introduce como URL de un servidor MCP en el cliente; no es una página de Swagger. Sólo acepta conexiones desde el equipo local y valida Host y Origin. Uvicorn ignora cabeceras de proxy; no se debe publicar con un túnel o proxy que convierta visitantes externos en clientes locales. No se ha desplegado este servidor en Azure. Los procesos deben permanecer activos.

Para `stdio`, el cliente inicia el proceso y se comunica por su entrada/salida estándar. Comando desde el repositorio:

```powershell
.\scripts\start-mcp.ps1
```

No imprime un mensaje de bienvenida: stdout se reserva al protocolo JSON-RPC; los logs se escriben en stderr. No requiere mantener un proceso HTTP MCP adicional. En clientes con configuración `mcpServers`, adapta estas rutas absolutas al equipo:

```json
{
  "mcpServers": {
    "inside-game": {
      "command": "D:/ruta/al/repositorio/.venv/Scripts/python.exe",
      "args": ["-m", "inside_game.mcp_server"],
      "env": {
        "INSIDE_GAME_MCP_API_URL": "http://127.0.0.1:8000"
      }
    }
  }
}
```

El comando Python funciona desde cualquier directorio si el paquete está instalado. Para cargar `.env.local`, configura el cliente para ejecutar `powershell.exe -NoProfile -File D:/ruta/al/repositorio/scripts/start-mcp.ps1` mediante sus campos `command` y `args`. Este archivo de configuración es un ejemplo de formato habitual; cada cliente puede usar su propio formato.

## Configuración

`scripts/start-mcp.ps1` carga las variables `INSIDE_GAME_*` desde `.env.local` sin ejecutar su contenido. No sobrescribas un archivo local existente. El comando Python directo usa variables de entorno, no carga ese archivo automáticamente.

| Variable | Valor por defecto | Uso |
|---|---|---|
| INSIDE_GAME_MCP_API_URL | http://127.0.0.1:8000 | Origen de la API, propiedad del servidor; el agente no puede cambiarlo |
| INSIDE_GAME_API_KEY | vacía | Bearer del MCP hacia la API, si ésta exige autenticación |

Una API en otro equipo requiere HTTPS y una clave de al menos 32 caracteres. No se aceptan credenciales, rutas, query strings ni fragmentos en la URL. El cliente HTTP valida TLS, no sigue redirecciones y no usa proxies del entorno. No introduzcas claves en Git, instrucciones del agente ni argumentos de herramientas.

## Herramientas y uso por el agente

`tools/list` devuelve 34 herramientas, cada una con descripción en español, `inputSchema`, `outputSchema` y anotaciones de lectura, sin efectos destructivos. El detalle de las operaciones, métricas, coordenadas y límites está en [api.md](api.md). Las 121 capacidades del catálogo de diseño no son 121 herramientas independientes.

Secuencia habitual:

1. `describe_dataset` para conocer cobertura y limitaciones.
2. `list_matches` y `find_entities` para identificar partido, equipo o jugador.
3. `get_match_context` para participantes e intervalos.
4. Consultas específicas como `get_shots`, `get_sequences` o `get_heatmap`.
5. Cálculos espaciales como `get_team_shape` o `get_space_coverage` cuando la consulta lo requiera.

Ejemplo con el cliente oficial, con la API y el MCP HTTP activos:

```python
import asyncio
from mcp import Client

async def main():
    async with Client("http://127.0.0.1:8001/mcp") as client:
        tools = await client.list_tools()
        result = await client.call_tool("get_shots", {
            "match_id": 900001,
            "team_id": 1,
            "outcome": "on_target",
            "view": "summary"
        })
        if result.is_error:
            print(result.content)
        else:
            print(result.structured_content["data"])  # total: 6

asyncio.run(main())
```

Las respuestas exitosas contienen el mismo objeto de la API en `structuredContent` y como JSON en `content`, para clientes que sólo leen texto. Conservan `operation_id`, `method_id`, `request_id`, `scope`, `data`, `provenance`, `coverage`, `coordinates`, `pagination` y `warnings`. Un cursor de `pagination.next_cursor` debe acompañar los mismos argumentos de la consulta; no cambia el total del resultado.

Los errores de herramienta devuelven `isError=true` y un objeto JSON `error` en el contenido de texto. No llevan un objeto de éxito inventado ni `structuredContent` incompatible con el esquema de salida. Códigos principales: `INVALID_ARGUMENT`, `UNREGISTERED_OPERATION`, `UNAUTHORIZED`, `NOT_FOUND`, `RATE_LIMITED`, `BUSY`, `API_UNAVAILABLE`, `RESPONSE_TOO_LARGE` e `INVALID_API_RESPONSE`. Los errores HTTP se traducen a mensajes públicos y no reflejan detalles internos del servidor.

## Límites y significado de los datos

El MCP vuelve a validar los argumentos antes de llamar a la API. Rechaza propiedades desconocidas, SQL, nombres de herramientas no registrados, valores fuera de los enums y parámetros fuera de rango. La API conserva sus propias validaciones y permisos de lectura. Hay límites por proceso de 120 llamadas válidas por minuto, cuatro llamadas simultáneas y 35 segundos por consulta. El HTTP MCP limita el cuerpo completo a 64 KiB; los argumentos por stdio también se limitan a 64 KiB. La respuesta de la API se lee en streaming hasta 1 MiB; MCP añade el envoltorio y duplica el objeto como texto para compatibilidad.

Un resultado vacío y una falta de cobertura tienen significado distinto; el agente debe leer advertencias y cobertura. El tracking es sintético a 1 Hz, el xG es ilustrativo, Voronoi es área geométrica y no probabilidad de control. El MCP no añade modelos calibrados ni convierte un indicador geométrico en una conclusión de rendimiento real.

## Verificación

Pruebas sin conexión a Azure, con una API de fixture y cliente MCP real en memoria:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Pruebas explícitas de integración contra la API activa y Azure SQL, sin modificar filas:

```powershell
.\.venv\Scripts\python.exe scripts/verify_mcp.py --transport stdio
.\.venv\Scripts\python.exe scripts/verify_mcp.py --transport streamable-http
```

La primera inicia y cierra su subproceso MCP. La segunda usa el servidor de `127.0.0.1:8001/mcp`. Verifican las 34 operaciones, procedencia, totales conocidos, tracking, Voronoi y rechazo de SQL. Evidencias: [stdio](mcp-verification-stdio.json) y [HTTP](mcp-verification-streamable-http.json).

Para QA funcional con consultas reales sobre los diez partidos:

```powershell
.\.venv\Scripts\python.exe scripts/qa_queries.py
```

Requiere ambos servidores activos y variables de entorno de la API si se cambia su configuración. Contrasta los goles con el marcador, el xG agregado con los tiros individuales, filtros de equipo/período/resultado/altura, paginación completa, cronologías, mapas, entradas y duelos. Revisa tracking antes y después de una sustitución y compara resultados de la API por TCP con ambos transportes MCP. También exige el rechazo de consultas inválidas y de cursores usados con otros filtros. No modifica filas SQL.

La evidencia [query-qa-report.json](query-qa-report.json) contiene argumentos de consultas, estados HTTP y comprobaciones de negocio. Estos controles corresponden a la carga sintética auditada, no certifican realismo estadístico de fútbol profesional ni sustituyen pruebas de carga.

Al probar una sustitución se usa el intervalo efectivo de `get_match_context`: en esta carga a 1 Hz, el evento identifica al saliente y el reemplazo ocupa su posición desde la muestra del segundo siguiente. El QA contrasta ambos frames con el fin del intervalo del saliente y el inicio del entrante.
