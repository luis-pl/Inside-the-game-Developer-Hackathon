# Agente de insights y comunicación HTTP

El agente interpreta una intención en texto, recupera evidencia del agente de
datos cuando falta, selecciona las piezas del MCP y entrega una página HTML.
También modifica páginas existentes sin regenerar su evidencia innecesariamente.
El intérprete y el analista pueden consumir el contrato; sus implementaciones
conversacionales siguen siendo independientes de este servicio.

El transporte es **HTTP/JSON propio, versionado**, bajo `/a2a/v1/`. Ese nombre
de ruta no significa compatibilidad con una versión del estándar A2A externo.
El MCP deportivo y el MCP de composición conservan sus protocolos existentes.

También se conserva la implementación de tu compañero: `InsightsAgent` con
planificador/resolvedor, interfaz web y transporte SDK A2A, documentada en
[insights-agent.md](insights-agent.md) y [a2a.md](a2a.md). Ambas entradas reutilizan
la biblioteca y el MCP. Para crear/modificar páginas con revisiones y texto del
analista usa el servicio de este documento (`DashboardBuilder` en `page_builder.py`).
La fachada `dashboard_builder.py` exporta ambos ejecutores. La cadena A2A conserva
sus contratos `AskRequest`; el HTTP con revisiones utiliza `InsightRequest`.

## Ejecutar

```powershell
.\.venv\Scripts\python.exe -m inside_game.agents_cli --port 8085
```

El comando carga asignaciones de `.env`/`.env.local` sin evaluarlas como código.
Reutiliza Beam Free por OpenCode Go, la sesión CLI y la comprobación de precio
cero configuradas. No compra crédito, activa Extra Usage ni cambia de proveedor.
`INSIDE_GAME_OPENCODE_FREE_ONLY=1` debe mantenerse. No es necesario ejecutar
OpenAI/Azure inference adicional ni un analista para recibir su texto.

En local puede leer la credencial privada individual `agent-data` ya configurada
en `INSIDE_GAME_DATA_MCP_CREDENTIAL_FILE`, incluyendo su caducidad. Sólo conserva
su hash en el registro de autenticación del servicio. No imprime ni empaqueta
esa credencial. Para varios titulares configura `INSIDE_GAME_AGENT_CREDENTIALS_JSON`
con los registros de hashes de `KeyRegistry`: ID, nombre, rol developer/agent,
caducidad Unix, SHA256, enabled y operaciones permitidas existentes.

Ambos servicios deben conocer los mismos titulares autorizados. El bearer de
la petición se conserva al delegar al agente de datos y al MCP deportivo, de
modo que la API deportiva mantiene sus permisos y trazabilidad originales.
No se sustituye al usuario por una clave administrativa compartida.

Por defecto los dos endpoints están en el mismo proceso, pero insights llama
a data mediante un cliente HTTP real. `INSIDE_GAME_DATA_AGENT_URL` permite separar
sus procesos/contenedores. El destino lo configura el anfitrión, nunca el modelo;
los destinos remotos exigen HTTPS y no se siguen redirecciones.
`INSIDE_GAME_AGENT_ALLOWED_HOSTS` permite declarar el hostname del contenedor.
Esta implementación inicia un servicio local; no despliega uno nuevo en Azure.

## Contrato para intérprete y analista

Todas las rutas excepto `/health` requieren `Authorization: Bearer <clave>`.
Las claves no van en query strings, solicitudes naturales ni argumentos de tools.

| Método y ruta | Entrada / salida |
|---|---|
| `POST /a2a/v1/data` | `DataRequest` → `DataResult` original |
| `POST /a2a/v1/insights` | `InsightRequest` → estado, página, revisión, URI, bloques y tiempos |
| `GET /a2a/v1/reports/{report_id}` | Plan y estado actuales del titular |
| `GET /a2a/v1/reports/{report_id}/revisions/{revision}/html` | HTML autenticado de una revisión |
| `GET /health` | Estado del proceso y versión del protocolo; no comprueba SQL/modelo |

Ejemplo de creación:

```json
{
  "request_text": "Crea mapa de tiros y evolución del xG del partido 900001",
  "context": {"match_ids": [900001]},
  "analyst": {
    "text": "Datos sintéticos de demostración; el xG es ilustrativo.",
    "evidence_ids": []
  }
}
```

`request_id` es un UUID opcional generado si falta. Para reintentar una petición
debe conservarse el mismo UUID y cuerpo: no vuelve a ejecutar inferencia si ya
terminó. Un UUID reutilizado con otro cuerpo, o todavía en ejecución, devuelve
409. Se devuelve `X-Request-ID`; `data_request_ids` y `data_runs` enlazan cada
delegación con sus estados, notas y errores, sin secretos.

`data_result` permite que el anfitrión aporte un resultado original del agente de
datos en vez de recuperarlo otra vez. Su evidencia completa queda fuera del
contexto LLM: el modelo ve un catálogo con IDs, filtros, procedencia, cobertura
y previews acotados. El renderer conserva los originales dentro del HTML.

El texto `analyst.text` se inserta literalmente, escapado como texto. El modelo
constructor no puede reemplazarlo por análisis o cifras propias dentro del render.
Sus referencias, si existen, deben corresponder a evidencia disponible.

El resultado `complete` significa que todos los bloques están disponibles y
las recuperaciones de datos fueron completas. `partial` conserva limitaciones
de la fuente o una recuperación incompleta aunque ciertos gráficos estén
disponibles. `needs_clarification` contiene una pregunta y no crea una página.
`error` deja intacta la revisión anterior. `unsupported` explica una intención
no atendible. El HTTP200 contiene el estado funcional; los errores de contrato,
autenticación y conflicto usan 422, 401, 404 o 409 respectivamente.

## Modificar una página

```json
{
  "request_text": "Añade una red del equipo 1 en el primer tiempo; conserva las otras secciones",
  "report_id": "UUID_DEVUELTO_AL_CREAR",
  "expected_revision": 1
}
```

Después puede pedirse cambiar colores, títulos, layout, orden, umbral de enlaces
o quitar/añadir gráficos. `expected_revision` es obligatorio al modificar. Un
conflicto devuelve 409; el cliente recupera la revisión actual antes de reintentar.
El contexto y texto del analista anteriores se conservan si no se reemplazan.

La herramienta `update_report` recibe patches tipados: `add_blocks`,
`replace_blocks`, `remove_block_ids`, `order_ids`, `title`, `teams`. La aplicación
del patch conserva automáticamente los bloques no afectados, valida IDs y orden
y termina usando `render_report` del MCP. No hay evaluación de código generado.

La publicación es atómica: un fallo del modelo, un timeout o un patch inválido
no destruyen la página anterior. Las versiones son inmutables y privadas del
titular autenticado. No hay acceso a páginas de otra credencial por adivinar UUIDs.

## Herramientas, prompt y presupuestos

- Prompt editable: `prompts/insights_agent.md`; su hash figura en cada respuesta.
- Cinco tools MCP: descubrir, describir, validar, render individual y página.
- Tools del ejecutor: `request_data`, `update_report`, `finish_insight_request`.
- El modelo decide la selección; los contratos y renderer controlan los datos,
  HTML, CSP, límites y estados. No puede elegir URL, credencial ni modelo.
- Deadline HTTP de insights: 55 s, incluyendo inicialización del proveedor. El
  ejecutor tiene el mismo límite, hasta seis turnos y diez llamadas a tools.
- La delegación a data recibe hasta 40 s o el tiempo restante menos una reserva.
  `/data` admite `X-Agent-Deadline-Ms` de 1000–45000, establecido por el anfitrión.
- Superar el deadline devuelve un error explícito; el plazo no garantiza una
  página completa si la nube, el modelo o la recuperación no responden a tiempo.
- Entrada/evidencia: hasta 8 MiB, cien evidencias. HTML: hasta 16 MiB, cuarenta
  bloques. Recomendación del prompt para resúmenes: tres a ocho bloques útiles.
- Almacén demo: hasta veinte páginas por titular, cinco revisiones por página,
  una hora de vida y 128 MiB de HTML acumulado para el proceso. El cache de
  idempotencia tiene hasta mil mensajes; no duplica los HTML/evidencias.
- El almacén vive en memoria: reiniciar elimina los enlaces. Descargar el HTML
  permite conservarlo. Varias réplicas necesitan un almacén compartido futuro.
- Límite de sesenta peticiones/minuto por titular y ocho peticiones concurrentes;
  el límite incluye delegaciones HTTP. Se rechazan mensajes mayores del presupuesto.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/qa_insight_agent.py
```

La suite unitaria/integración usa modelos programados y MCP real, sin consumir
inferencia. Prueba XSS, identidad, HTTP de data, correlación, idempotencia,
revisiones antiguas, publicación concurrente, patches, timeout y conservación del
análisis. Es independiente de la evaluación del modelo seleccionado.

`qa_insight_agent.py` sí usa Beam Free real, autenticado por la sesión autorizada,
con la comprobación de precio cero antes de cada inferencia. Crea tres páginas,
amplía una con otra gráfica y modifica sus colores/layout. Guarda HTML, estados,
trazas y mediciones en `.temp/insights/agent-qa/`. La procedencia sintética del
partido `900001` y el xG ilustrativo permanecen visibles. La prueba no autoriza
modelos pagos ni cambiar el plan para superar una cuota.

Los HTML exportados pueden verse con el servidor estático local:

```powershell
.\.venv\Scripts\python.exe -m http.server 8083 --bind 127.0.0.1 --directory .temp/insights
```

Informe medido y límites: `docs/insight-agent-verification.json`. Los tiempos
registrados son de ejecuciones concretas; no son una garantía ante un arranque
en frío o una incidencia del proveedor.

## Integración del trabajo paralelo

Durante las pruebas se publicó y fusionó `feature/insights-agent-a2a`. Se
conservan su planificador, resolvedor, perfiles, web, transporte SDK A2A y
mejoras visuales. La entrada A2A usa ahora un deadline por defecto de 55 s
(planificador: 40 s). El HTTP con revisiones conserva la identidad individual
y el texto del analista. La biblioteca comparte contratos y renderer; el MCP
conserva también la evidencia citada por el analista aunque no la use un gráfico.
