# Revisión del agente de datos · 24 de octubre de 2026

El agente puede consultar mediante Beam Free → MCP → API → Azure SQL y entregar
evidencia original para otros agentes. Se revisaron el prompt, el ejecutor, las
tools expuestas y la salida; se ejecutaron pruebas reales, no sólo simulaciones.
Instrucciones para probarlo: [guía de ejecución](run-and-review-data-agent.md).

## Hallazgos y correcciones

| Hallazgo | Efecto | Corrección y evidencia |
|---|---|---|
| Preview del catálogo limitado a ocho filas | Los diez partidos reales quedaban ocultos detrás del historial sintético; el modelo generalizaba su competición y hacía búsquedas adicionales | Se muestran completas las páginas de catálogo, hasta el máximo contractual de 200 filas. Regresión local y repetición de ambigüedad/resolución de nombres |
| Se podía omitir una consulta analítica entera al seleccionar evidencia | `complete` podía devolver sólo uno de los jugadores ya consultados | Se rechaza `OMITTED_QUERY_EVIDENCE` hasta incluir la consulta o declarar otro estado. Prueba con dos jugadores |
| Finalización y consultas en el mismo lote | Retornar al encontrar finish podía descartar llamadas posteriores | Se rechaza el lote con `FINISH_MUST_BE_SEPARATE`, conservando una respuesta por call_id. Regresión local |
| Argumento rechazado por API contaminaba el estado permanentemente | Aunque Beam corrigiera la consulta y recuperara todos los datos, el resultado quedaba parcial | Un `INVALID_ARGUMENT` anterior a cualquier página se trata como corregible, igual que la validación local. Un fallo después de recuperar páginas sigue siendo incompleto; los fallos NOT_FOUND/red mantienen el tratamiento conservador |
| Tiros disponibles y xG ausente se marcaban completos | Las notas reconocían la falta pero el estado no reflejaba que faltaba una variable pedida | Prompt con definición precisa y ejemplo de solicitud mixta. SkillCorner devuelve `partial` con sus tiros y advertencia explícita de xG ausente |
| Búsquedas de nombres y filtro de equipo | Una ejecución agotó el límite de tokens y consultó ambos equipos pese a pedir uno | Se reutilizan IDs del catálogo, se explica búsqueda literal por fragmentos y se exige conservar team_id. El límite observado pasa de 100.000 a 160.000 tokens, manteniendo límites de turnos, tiempo, llamadas y precio cero |
| El verificador comparaba literalmente cursores recién firmados | Falso fallo de preservación aunque los datos fueran idénticos | Compara estructura de paginación y campos estables; el token opaco puede cambiar por caducidad. Regresión con datos, advertencias y final de página diferentes |

El prompt ahora ordena la recuperación por entregas, resolución de referencias,
elección de tools, comprobación de cobertura y finalización. Distingue 1 Hz por
defecto de los 5 Hz solicitables explícitamente, intervalos por período y campos
ausentes de las fuentes reales. Se conserva una sola fuente editable en
`prompts/data_agent.md`, con versión y SHA-256 en cada resultado.

## Pruebas realizadas

- **155 pruebas Python aprobadas**, incluidas las regresiones anteriores.
- **18 solicitudes reales** con catálogo completo: tiros y coordenadas, tres
  jugadores, comparaciones, varios partidos, duelos/intercepciones, segundo tiempo,
  paginación, geometría, ambigüedad, vídeo no disponible, SQL no permitido,
  presión, tracking real a 5 Hz, xG ausente, nombres reales, solicitud mixta,
  score no disponible e intervalo dividido.
- La última pasada completa dio **16/18**. Los dos casos afectados por recuperación
  de argumentos y comparación de cursores pasaron sus repeticiones específicas
  tras las correcciones. No se presenta esto como una pasada única de 18/18.
- La preservación coteja directamente datos, alcance, procedencia, cobertura,
  coordenadas, advertencias, método y estructura de paginación contra MCP.
- El comando de PowerShell documentado terminó con `complete`, **dos llamadas
  MCP y tres turnos de Beam Free**: contexto y 24 tiros del partido real 900011.
- Visor local HTTP200, catálogo HTTP200 y episodio real de 60 segundos con
  **300 frames a 5 Hz**. El launcher compiló el frontend correctamente.

Resultados estructurados: [data-agent-review-verification.json](data-agent-review-verification.json).
Los resultados completos de sesión quedan en `.temp/agent-review/` y
`.temp/prueba-agente.json`, fuera de Git.

## Límites que siguen vigentes

Los 18 ejemplos no cubren cada parámetro de las 34 operaciones ni cualquier
redacción posible. La selección semántica y las notas siguen siendo decisiones
del modelo; la validación de esquema no demuestra que toda solicitud natural se
haya interpretado correctamente. El control de omisiones protege consultas ya
ejecutadas, no puede detectar por sí solo una intención que nunca se convirtió
en consulta. El consumidor debe comprobar evidencia, alcance y advertencias.

La prueba inicial también mostró un extremo temporal ambiguo: «hasta el segundo
130» fue interpretado inclusivamente. El caso final especifica `[0,130)`, conforme
al contrato. Si el producto requiere otra convención de reloj debe declararla.

El agente no tiene memoria entre invocaciones del CLI ni servidor A2A propio.
No produce un análisis deportivo o dashboard, y no inventa vídeos, xG real,
posiciones entre muestras o scores tácticos calibrados. No se cambiaron modelo,
plan, facturación ni Extra Usage; se conserva `INSIDE_GAME_OPENCODE_FREE_ONLY=1`.
