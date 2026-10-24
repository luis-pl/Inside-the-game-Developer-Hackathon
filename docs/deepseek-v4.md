# Prueba de DeepSeek V4 en Azure

El titular autorizó probar DeepSeek V4. Se eligió `DeepSeek-V4-Flash`, versión
`2026-04-23`, Global Standard, sobre el recurso Foundry existente
`ai-inside-game-01a160e1-ca`. El despliegue se llama `deepseek-v4-flash`.
No se compró capacidad provisionada ni se modificó la API, MCP o SQL.

## Resultado y alcance

- Autenticación Azure CLI y llamada de función mínima: superadas, 371 tokens.
- Catálogo completo de 34 herramientas: dos casos ejecutados y ninguno completo.
  Tiros y comparación de equipos terminaron `partial` con `MODEL_RATE_LIMITED`.
  Se conservó la evidencia recuperada y se cotejó directamente con MCP.
- Catálogo diagnóstico de dos herramientas (`get_shots`, `describe_dataset`):
  consulta de tiros superada. Partido 900001, equipo 1, filtro `on_target`:
  seis eventos sintéticos con tiempos y coordenadas, iguales a los del MCP.
  Consumió 10.525 tokens en dos turnos, sin errores.

La prueba acotada no demuestra que funcionen todas las consultas del agente.
El candidato sigue sin seleccionarse como modelo predeterminado. El catálogo
completo produjo aproximadamente 24.000 tokens por primer turno y el despliegue
tiene 20.000 tokens/minuto y 20 solicitudes/minuto. Las llamadas siguientes fueron
limitadas incluso con el reintento existente. Antes de activarlo hay que reducir
el contexto enviado o conseguir más cuota y repetir la evaluación completa.

Los tokens reportados por estas respuestas suman 59.223 incluyendo diagnóstico y
ambos casos fallidos. No son el coste monetario ni garantizan que todas las
métricas de facturación estén procesadas.

## Informes reproducibles

- [Despliegue y estado](../deployment/deepseek-v4.json).
- [Catálogo completo: falló](deepseek-v4-verification.json).
- [Catálogo reducido: pasó](deepseek-v4-scoped-verification.json).
- `scripts/verify_data_agent.py --case shots_count_time_location --case compare_two_teams --private-file RUTA_PRIVADA --report docs/deepseek-v4-verification.json`.
- `scripts/verify_deepseek_v4.py` reproduce únicamente el diagnóstico reducido.

Ambos comandos requieren las variables de Azure y MCP cargadas en el proceso:

```text
AZURE_OPENAI_ENDPOINT=https://ai-inside-game-01a160e1-ca.services.ai.azure.com/
AZURE_OPENAI_DEPLOYMENT=deepseek-v4-flash
INSIDE_GAME_MODEL_API=chat_completions
INSIDE_GAME_MODEL_AUTH=azure_cli
INSIDE_GAME_DATA_MCP_URL=https://<api>.azurecontainerapps.io/mcp
INSIDE_GAME_DATA_MCP_CREDENTIAL_FILE=<ruta privada de agent-data.json>
```

Los scripts no cargan `.env.local` automáticamente. La configuración local
predeterminada sigue sin modelo seleccionado. Nunca usar el archivo administrativo
de credenciales ni copiar claves al repositorio.

## Crédito y facturación

El titular actualizó su suscripción a pago por uso. La consulta de preflight
confirmó `PayAsYouGo_2014-09-01`, límite de gasto `Off` y un saldo reportado de
USD200 en la API de créditos. Ese saldo fue consultado antes de la inferencia y
puede no reflejar consumo reciente; no equivale a una garantía de cobro cero.
Esta prueba no cambió la suscripción ni contrató un servicio de Marketplace.
El despliegue utiliza los medidores de Foundry vendido por Azure.

No se publica una estimación monetaria: la página pública no expuso importes y
la Retail Prices API devolvió HTTP429. No interpretar un importe desconocido
como cero. El presupuesto de USD100 de la demo sigue siendo de seguimiento;
no corta el consumo al alcanzarlo.

Referencias: [DeepSeek y llamadas a herramientas](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure#deepseek-models-sold-by-azure),
[facturación de modelos](https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/deepseek/).
