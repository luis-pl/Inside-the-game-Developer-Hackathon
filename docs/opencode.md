# OpenCode Go y Console/Zen

El titular pidió usar el consumo incluido de Go. OpenCode documenta una API Go
para otros clientes, aunque la orienta a agentes de programación. La primera
interpretación del proyecto descartaba demasiado tajantemente ese acceso.
Nuestro cliente declara su identidad real de agente deportivo; no finge ser
OpenCode ni manipula el tráfico para eludir restricciones. La aceptación de este
uso por el servicio se comprobó en la prueba acotada descrita abajo; no se afirma
que exista una garantía de disponibilidad ni aceptación de cualquier volumen.

## Acceso actualizado: 24 de octubre de 2026

La autorización del CLI terminó correctamente. La sesión de cuenta y los
catálogos Go/Console responden HTTP200 con el token de la sesión y la cabecera
oficial `x-opencode-org-id`. La clave antigua de `auth.json` sigue devolviendo
HTTP401; no se utiliza como fallback de la sesión nueva.

El usuario autorizó seleccionar un modelo ilimitado gratuito. Go anuncia
Beam Free y LongCat 2.5 Preview Free como promociones temporales; el catálogo
real de esta cuenta contiene `beam-free`, pero todavía no
`longcat-2.5-preview-free`. Se selecciona explícitamente **Go / Beam Free**
con Chat Completions. Los modelos gratuitos del catálogo Console se mantienen
separados; no se cambia a ese plan.

Configuración local actual, sin secretos:

```text
INSIDE_GAME_MODEL_PROVIDER=opencode-go
INSIDE_GAME_OPENCODE_MODEL=beam-free
INSIDE_GAME_OPENCODE_API=chat_completions
INSIDE_GAME_OPENCODE_AUTH_MODE=cli_session
INSIDE_GAME_OPENCODE_FREE_ONLY=1
```

El cliente lee únicamente la cuenta y workspace activos de `opencode.db` en
modo de sólo lectura. No copia tokens ni modifica la base del CLI. Relee la
sesión antes de cada petición; si caduca, se detiene con
`MODEL_CLI_SESSION_EXPIRED`. `opencode console orgs` permite al CLI renovar su
propia sesión; si falla, reconectar mediante su flujo oficial.

En modo gratuito consulta la configuración oficial de la cuenta antes de
cada petición de inferencia. Exige un modelo de la lista gratuita permitida,
disponible en Go, con precios de entrada, salida y caché cero. Si falta la
información o cambia el precio, produce `MODEL_FREE_STATUS_UNVERIFIED` y no
envía la inferencia. Este control no modifica Extra Usage ni la facturación.

La primera prueba acotada quedó parcial por `API_UNAVAILABLE` del servicio de
datos (`beam-free-scoped-verification.json`). Tras comprobar el MCP, la repetición
pasó: `beam-free-scoped-retry-verification.json`, estado completo, argumentos
correctos y evidencia cotejada directamente contra el MCP. La autenticación y
los precios cero publicados constan en `opencode-auth-verification.json`.
Las 54 pruebas locales del conector, agente y selección pasaron. Tras resolver
los conflictos de integración también pasaron las 149 pruebas Python, las 42 de
frontend y su compilación. Esto no sustituye la evaluación remota del corpus
completo. Evidencia: [verificación de integración](integration-verification.json).

Implementación oficial consultada para la sesión y las cabeceras:
[cliente 1.17.15](https://github.com/anomalyco/opencode/blob/v1.17.15/packages/opencode/src/account/account.ts).

## Historial anterior: clave API antigua

La credencial local opencode-go devolvió HTTP401 al leer el catálogo en ambas
rutas oficiales, actual y anterior:

- https://opencode.ai/inference/go/v1/models
- https://opencode.ai/zen/go/v1/models

No se consumió inferencia ni se confirmó uso restante, saldo o acceso al modelo.
Se solicitó reconectar con /connect → OpenCode Go. El proveedor Go y Luna están
configurados localmente, pendientes de autenticación y evaluación real del MCP.
Las pruebas locales simuladas no equivalen a tener un modelo remoto operativo.

## Configuración histórica con clave API (no activa)

```text
INSIDE_GAME_MODEL_PROVIDER=opencode-go
INSIDE_GAME_OPENCODE_MODEL=gpt-6-luna
INSIDE_GAME_OPENCODE_API=responses
INSIDE_GAME_OPENCODE_AUTH_FILE=C:/Users/<usuario>/.local/share/opencode/auth.json
```

scripts/start-data-agent.ps1 carga estos ajustes desde .env.local, ignorado por
Git. El CLI directo y los scripts de evaluación requieren las variables cargadas
en el proceso. El proveedor lee únicamente la entrada del plan seleccionado:
opencode-go para Go u opencode para Console/Zen. No copia las claves al repo.
También admite INSIDE_GAME_OPENCODE_API_KEY inyectada como secreto del proceso.

El destino Go es fijo: https://opencode.ai/inference/go/openai/v1. Luna utiliza
Responses. Kimi K3 utiliza kimi-k3 y chat_completions según el catálogo, pero no
se selecciona ni se consume por su cuenta cuando falla Luna.

El cliente envía Bearer, el User-Agent inside-game-sports-data-agent/0.0.0 y
x-opencode-session con el UUID de la solicitud. Mantiene la sesión entre turnos
y reintentos y aísla conversaciones concurrentes mediante ContextVar. Las claves
Azure y MCP se conservan separadas. El prompt no permite cambiar el proveedor.

## Uso y facturación

Go tiene ventanas de uso de cinco horas, semana y mes. Eso no equivale a una
cuota TPM de Azure ni demuestra que haya saldo prepago Console. El uso restante
se consulta en OpenCode. Los créditos Azure no se transfieren a este servicio.

El cliente no compra crédito, cambia planes, activa recargas ni cambia a Console
por un error. HTTP401/403 detienen autenticación; HTTP402 produce
MODEL_BILLING_REQUIRED. Extra Usage y recargas son preferencias de la cuenta:
este cliente no las consulta ni modifica. El endpoint Go, por sí solo, no prueba
que estén desactivadas y no garantiza ausencia de cargos de la cuenta.

Console/Zen se configura por separado con INSIDE_GAME_MODEL_PROVIDER=opencode,
su credencial y saldo propios y el destino fijo
https://opencode.ai/inference/openai/v1. No es un fallback de Go.

## Pruebas

Las pruebas de tests/test_opencode_provider.py usan transporte simulado. Verifican
selección explícita del plan, destino fijo, Bearer, Responses/Chat Completions,
sesiones aisladas y ausencia de fallback ante HTTP401/402. Junto con el agente y
el control de selección, 51 pruebas locales pasaron. No validan la cuota efectiva
ni la aceptación del tráfico deportivo por Go.

Después de reconectar, cargar la configuración y evaluar con:

```text
python scripts/verify_data_agent.py --private-file RUTA_PRIVADA_AGENT_DATA --report docs/opencode-agent-verification.json
```

Ese comando consume el modelo configurado. Los informes previos de Azure no
certifican que OpenCode haya pasado las pruebas.

Fuentes: [API Go](https://opencode.ai/v2/docs/console/go/#where-can-i-use-it),
[endpoints y límites](https://opencode.ai/v2/docs/console/go/#endpoints),
[API Console](https://opencode.ai/v2/docs/console/api/inference/).
