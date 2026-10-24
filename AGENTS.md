# Inside the game: Developer Hackathon

Este repositorio prepara un sistema de analítica deportiva con cuatro agentes:
intérprete de solicitudes, agente de datos, analista deportivo y constructor de
dashboards. El paquete Python es `inside_game` y vive en `src/inside_game/`.

La estructura inicial contiene módulos reservados, sin implementación de agentes,
contratos, orquestación, API, CLI, proveedores de modelos ni servidores MCP/A2A.
Desarrollar esas funciones cuando la tarea correspondiente lo solicite.

La base Azure SQL, su esquema y los datos sintéticos existentes están documentados
en `database/azure-sql/`. Consultar su `README.md` y `DATA-QUALITY.md` al trabajar
con datos; conservar la identificación explícita de su procedencia sintética.
No guardar credenciales en el repositorio.

Consultar `docs/repository-structure.md` para localizar los módulos. Los archivos
de `drafts/` son referencias de diseño.

## Presupuesto autorizado

El titular exige cero pagos de su bolsillo. Usar únicamente servicios gratuitos
o consumo elegible cubierto por el crédito promocional vigente. El titular
actualizó personalmente la suscripción de Free Trial a pago por uso; Azure ya
reporta `PayAsYouGo_2014-09-01` y `spendingLimit=Off`. No cambiar la facturación ni
contratar servicios con cobros separados o no cubiertos por el crédito. Un
presupuesto/alerta de Cost Management no es un corte de consumo.
La cuota cero de un modelo no autoriza a cambiar la facturación para habilitarlo.
El presupuesto de trabajo autorizado es USD100 dentro del crédito disponible;
el seguimiento de Azure cubre `rg-inside-game-demo`. Se permite un modelo
alternativo compatible y cubierto por crédito, sujeto a la selección del titular.
El titular descartó GPT-OSS-120B: no seleccionarlo ni invocarlo; su despliegue y
evaluaciones previas se conservan como historial. Luna sigue sin cuota; su
solicitud fue rechazada. El titular autorizó probar DeepSeek V4, sin seleccionar
automáticamente otros modelos. Mantener separados diagnóstico acotado y QA del
catálogo completo.
Mantener explícito que el presupuesto de seguimiento no corta consumo.

El titular pidió usar OpenCode y confirmó que sólo tiene Go, sin saldo Console/Zen
confirmado. Autorizó intentar consumir el uso incluido por la API Go. Seleccionar
Go explícitamente, sin comprar crédito, habilitar recargas ni cambiar de Go a
Console como fallback. La documentación orienta Go a tráfico de programación;
declarar la identidad real del agente deportivo y conservar la sesión UUID, sin
fingir ser OpenCode. El 24 de octubre se autorizó la sesión del CLI; el catálogo
Go respondió HTTP200. La clave API antigua conserva HTTP401 y no se usa como
fallback. El titular pidió seleccionar el mejor modelo gratuito ilimitado
disponible: se eligió Beam Free, único de los dos anunciados que aparece en su
catálogo Go (LongCat 2.5 Preview Free todavía no aparece). Una prueba acotada
modelo → MCP → SQL pasó; no equivale a QA del corpus completo. Mantener
`INSIDE_GAME_OPENCODE_FREE_ONLY=1`: verificar precios cero antes de inferencia y
detenerse si falta esa confirmación. No cambiar facturación ni Extra Usage.
