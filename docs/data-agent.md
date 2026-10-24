# Agente de datos

Recibe texto del intérprete, analista o dashboard builder y contexto opcional.
Selecciona operaciones predeterminadas del MCP y sus parámetros; obtiene los
resultados mediante el servidor existente. Los números, eventos y coordenadas
de la salida son evidencia original del MCP conservada por código.

## Archivos

- `src/inside_game/agents/data_agent.py`: ejecutor y límites.
- `src/inside_game/agents/contracts.py`: mensajes de entrada/salida.
- `prompts/data_agent.md`: instrucciones editables, incluidas en el wheel.
- `src/inside_game/providers/models.py`: Responses (Luna), Chat Completions (GPT-OSS) y auth.
- `src/inside_game/tools/mcp_client.py`: conexión MCP autenticada.
- `tests/fixtures/data_agent_cases.json`: corpus de solicitudes deportivas.

## Configuración y ejecución

Requiere un proveedor que soporte llamadas a herramientas. La configuración
actual selecciona **Beam Free por OpenCode Go**, con sesión autorizada del CLI y
`INSIDE_GAME_OPENCODE_FREE_ONLY=1`. La autenticación respondió HTTP200 y una prueba
real acotada pasó, sin certificar el corpus completo. Ver [OpenCode](opencode.md).
Los ensayos anteriores de Azure se conservan como historial; si se usa Azure,
`AZURE_OPENAI_DEPLOYMENT` debe ser el nombre del despliegue. No se cambia de modelo
ni de proveedor por un fallo.

También se probó DeepSeek V4 Flash: el diagnóstico reducido pasó y los dos casos
con el catálogo completo fallaron por cuota. Sigue como candidato sin selección
predeterminada. Ver [informe y reproducción](deepseek-v4.md).

Hay un conector [OpenCode Go y Console/Zen](opencode.md), con selección explícita
mediante `INSIDE_GAME_MODEL_PROVIDER=opencode-go` u `opencode`. Go usa la sesión
actual del CLI: la clave API antigua sigue devolviendo HTTP401 y no es fallback.

Plantilla para un futuro despliegue aprobado, nunca parte del texto recibido:

```text
AZURE_OPENAI_ENDPOINT=https://<recurso-aprobado>.openai.azure.com
AZURE_OPENAI_DEPLOYMENT=<despliegue-aprobado>
INSIDE_GAME_MODEL_API=responses
INSIDE_GAME_MODEL_AUTH=azure_cli
INSIDE_GAME_REASONING_EFFORT=medium
INSIDE_GAME_DATA_MCP_URL=https://<app>.azurecontainerapps.io/mcp
INSIDE_GAME_DATA_MCP_KEY=<secreto individual agent-data>
```

En Azure usar `INSIDE_GAME_MODEL_AUTH=managed_identity` y, para identidad asignada
por usuario, `AZURE_CLIENT_ID`. La identidad necesita permiso de inferencia en el
recurso OpenAI. También se admite `api_key` con `AZURE_OPENAI_API_KEY` inyectada
desde un almacén de secretos. No colocar claves en prompts, argumentos de consola
ni Git. `default` usa DefaultAzureCredential sin navegador interactivo.

La clave MCP y la identidad Azure OpenAI son credenciales independientes. Una
clave MCP válida no concede permiso para consumir el modelo.

En local se puede usar `INSIDE_GAME_DATA_MCP_CREDENTIAL_FILE` con la ruta privada
del archivo individual `agent-data.json`, en lugar de copiar su clave al entorno.
El proceso lo lee sin imprimirla. No usar el archivo administrativo con todas las
claves ni guardar ese archivo dentro del repositorio.

Desde Windows, después de configurar las variables en `.env.local` (ignorado):

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\scripts\start-data-agent.ps1 -Text "Obtén los tiros a puerta del equipo 1 en el partido 900001 y sus ubicaciones"
.\scripts\start-data-agent.ps1 -RequestFile "solicitud.json" -OutputFile "resultado.json"
```

En otros sistemas, exportar las variables y ejecutar `inside-game-data-agent`
con `--text` o `--request-file`. El CLI directo no carga `.env.local`. La salida
es JSON; los logs de operaciones van a stderr, sin texto de solicitudes ni claves.
Los resultados pueden ser grandes: guardarlos fuera de Git cuando sean artefactos
de sesión. Códigos de salida: 0 completo, 2 aclaración/no soportado, 3 parcial, 1 error.

## Contrato para los otros agentes

```json
{
  "request_text": "Obtén mapas de ocupación y movimiento de estos jugadores durante el segundo tiempo",
  "context": {
    "match_ids": [900001],
    "player_ids": [106, 108, 110],
    "scope": {"kind": "period", "period": 2}
  }
}
```

Sólo `request_text` es obligatorio. El agente también acepta un string en `run()`.
`request_id` se genera si falta. Puede resolver nombres con MCP cuando no recibe
IDs; un partido o nombre ambiguo produce `needs_clarification` para el solicitante.

```python
from inside_game.agents.data_agent import DataAgent

# model y mcp son dependencias autenticadas, creadas por el proceso anfitrión.
result = await DataAgent(model).run(mensaje, mcp)
for item in result.evidence:
    datos = item.response.data
    coordenadas = item.response.coordinates
    cobertura = item.response.coverage
```

El analista y dashboard pueden invocar la misma interfaz. Cada ejecución mantiene
estado propio. Este módulo no implementa un servidor A2A ni el intérprete; el
adaptador de comunicación entre agentes debe autenticar a su llamador y pasar
este mensaje. `context` aporta contexto, no autorización de acceso.

La respuesta incluye `status`, `clarification`, notas de recuperación, `evidence`,
`issues`, modelo, versión de prompt y contadores. Cada evidencia tiene ID, query,
operación, parámetros y respuesta completa: `data`, `scope`, `provenance`,
`coverage`, `coordinates`, `pagination`, `warnings`, `method_id`, `request_id`.
El consumidor debe revisar cobertura/advertencias aunque el estado sea completo:
ese estado describe recuperación, no certifica validez científica o datos ausentes.
Las notas son texto del modelo; las cifras verificables están en la evidencia.

## Ejecución y límites

El catálogo se descubre con MCP y se cruza con el registro local de operaciones.
Se reutilizan sus contratos Pydantic, que rechazan propiedades desconocidas. No se
acepta SQL ni un destino de red enviado por el solicitante. Las funciones MCP se
publican al modelo con `strict=false` para conservar sus esquemas originales;
la validación efectiva es local y también ocurre en MCP/API. Responses admite
finalización con esquema estricto. El adaptador GPT-OSS expande referencias y
describe los enums numéricos como texto porque el renderizador Azure rechaza su
representación original; sus valores siguen validados con los contratos originales.
Este adaptador omite `strict` y usa `tool_choice=auto`, requerido por el servicio.
La finalización sólo permite seleccionar evidencia existente. Si el modelo devuelve
texto libre, se le pide corregir el protocolo hasta dos veces; ese texto nunca se
interpreta como datos ni como una llamada ejecutable.

La paginación es automática y conserva filtros. Las páginas se entregan por
separado; los agregados repetidos de cada página no deben sumarse entre sí.
El modelo recibe previews acotados, mientras el consumidor obtiene los valores
originales. Una selección incompleta o fallo de recuperación produce estado
parcial, aunque el modelo solicite marcar completo.

Límites predeterminados por solicitud: 16 turnos, 60 llamadas MCP incluyendo
reintentos, 20 páginas por consulta, 8 MiB de evidencia y 240 segundos. El consumo
observado se limita a 100.000 tokens; una respuesta ya en curso puede superar ese
umbral. Cada turno permite hasta 4.096 tokens de salida incluyendo razonamiento.
El proveedor hace un reintento transitorio y el ejecutor hace un reintento por
fallo transitorio MCP. La autenticación fallida detiene la solicitud. Estos límites
no sustituyen cuotas globales y concurrencia del proceso que hospede el agente.
Ante un límite de velocidad del modelo se respeta Retry-After hasta 60 segundos,
siempre dentro del plazo global de la solicitud. Si persiste, se devuelve
`MODEL_RATE_LIMITED` con evidencia parcial cuando ya se recuperaron datos.

Se usa razonamiento `medium`, sin `temperature`. En Responses se conserva la
salida de razonamiento cifrado entre turnos y `store=false`. En Chat Completions
se preservan los mensajes de llamada y sus IDs para asociarlos a sus resultados.

El tracking es sintético a 1 Hz, el xG ilustrativo, los eventos usan referencia
120x80 del equipo actuante y el tracking metros fijos. El agente no interpola ni
convierte métricas geométricas en un score táctico calibrado.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_data_agent.py -q
.\.venv\Scripts\python.exe scripts/verify_data_agent.py --private-file "RUTA_PRIVADA/agent-data.json"
```

Las pruebas unitarias usan un modelo programado y MCP real en memoria: comprueban
el ejecutor y preservación de evidencia, no la comprensión lingüística del modelo.
El segundo comando usa el modelo configurado, MCP y SQL reales; requiere despliegue, cuota, auth
Azure y la clave individual. Consume tokens y genera un informe con resultados
por caso. Nunca declarar superada esa evaluación basándose sólo en las unitarias.

El corpus cubre tiros, varios jugadores, varios partidos, defensa y duelos, relojes
por período, paginación, geometría, ambigüedad, capacidad ausente e intento de SQL.
La evaluación histórica con GPT-OSS está en `data-agent-verification.json`: doce casos
superados y cotejo de la evidencia contra MCP. El intento de SQL/secretos fue
rechazado por el proveedor (`MODEL_REQUEST_REJECTED`) antes de llamadas de datos;
se acepta ese fallo cerrado o una respuesta `unsupported`, nunca un error de
red/autenticación como prueba de rechazo seguro. El informe distingue segmentos
de ejecución y verifica cada combinación jugador/operación solicitada.

El informe `model-cost-verification.json` comprueba oferta, límite de gasto,
presupuesto y tokens registrados. Su coste es una estimación del modelo según
tarifas consultadas; no es una factura, saldo restante ni coste de toda la demo.
Los USD0,135167 corresponden al acumulado de inferencia registrado durante pruebas
y diagnósticos, no al precio de una consulta individual.

El comando `scripts/verify_data_agent_transport.py --private-file RUTA/agent-data.json`
prueba el ejecutor contra MCP y SQL reales usando planes controlados, sin LLM.
Su informe separado declara `llm_used=false`; no prueba comprensión del texto.

## Modelo y presupuesto en esta suscripción

Se desplegó y evaluó `gpt-oss-120b`, versión 1, GlobalStandard, en el recurso
`ai-inside-game-01a160e1-ca` y proyecto `inside-game`. Esta es inferencia de un
modelo vendido por Azure, sin VM/GPU dedicada, compromiso provisionado ni compra
de Marketplace. Posteriormente el titular lo descartó: el despliegue se conserva,
pero no está seleccionado ni configurado para ejecutar el agente. El acceso usado
en las pruebas fue Azure CLI con rol de inferencia en el recurso.
La configuración local no contiene claves de modelo; la clave MCP se lee del
archivo privado individual. Los otros miembros necesitan permiso de inferencia
propio si ejecutan el agente localmente; la clave de la API de datos es independiente.

Hay un presupuesto de seguimiento de USD100 para TODO `rg-inside-game-demo`, no
sólo inferencia, registrado en `deployment/demo-budget.json`. Es anual para evitar
que se reinicie al cambiar el mes durante la hackathon. No envía correos y no
detiene consumo automáticamente. Esa configuración se creó cuando la suscripción
era Free Trial con `spendingLimit=On`; el titular la actualizó posteriormente a
pago por uso y Azure ahora reporta `spendingLimit=Off`. Ninguno de los scripts
cambia la oferta de suscripción.

Los precios públicos consultados en la Retail Prices API de Azure para GPT-OSS
Global fueron USD0,15 por millón de tokens de entrada y USD0,60 por millón de
salida. Son tarifas consultadas, no un saldo, una reserva monetaria ni una factura.
La capacidad TPM asignada controla velocidad, no equivale a reservar USD100.
Uso de scripts: `configure_agent_model.py` bloquea la reactivación del modelo
descartado antes de acceder a Azure;
`configure_demo_budget.py` registra el objetivo tras verificar moneda USD y límite.

### Diagnóstico de Luna

Se creó el recurso `aoai-inside-game-01a160e1-ca`, pero Azure rechazó el despliegue
mínimo de Luna con `InsufficientQuota`: uso 0, límite 0. La suscripción indica
`FreeTrial_2014-09-01`, límite de gasto activado y Foundry `Free Tier`. Se comprobó
cuota cero en Canada Central, East US 2, Sweden Central y West US 3. No se cambió
la facturación. GPT-OSS se evaluó como alternativa con cuota y después fue
descartado por el titular; ambos estados están en `deployment/agent-model.json`.

El crédito monetario y la cuota de inferencia son controles distintos. Microsoft
indica que la elegibilidad de cuotas depende también de la oferta e historial:
[cuotas de Azure OpenAI](https://learn.microsoft.com/en-us/azure/foundry/openai/quotas-limits).
Actualizar una cuenta gratuita conserva el crédito restante hasta su vencimiento
original de 30 días, pero habilita posibles cargos de pago por uso:
[actualización de cuenta](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/upgrade-azure-subscription).
El titular ha establecido cero pagos personales. Posteriormente decidió actualizar
su cuenta a pago por uso; el objetivo sigue siendo consumir sólo crédito vigente,
sin adquirir servicios con cobros separados ni asumir que el presupuesto corta uso.
Destinar parte del crédito a modelos no habilita una cuota técnica en cero.
La documentación general de Azure indica que Free Trial no es elegible para
aumentos de cuota:
[límites de suscripción](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/azure-subscription-service-limits#how-to-manage-limits).
La vía a consultar con los organizadores es un despliegue compartido o una
suscripción patrocinada con cuota, sin facturación personal; su disponibilidad
no está confirmada. El código puede usar otro despliegue compatible configurado,
pero no lo selecciona por su cuenta. Actualizar a pago por uso no garantiza cuota.

El [límite de gasto](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/spending-limit)
se aplica al crédito de la suscripción; Azure no permite límites personalizados.
Un [presupuesto de Cost Management](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets)
sirve para seguimiento y alertas y no detiene automáticamente el consumo.
