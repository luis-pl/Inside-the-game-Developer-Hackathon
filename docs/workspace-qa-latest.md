# QA del workspace: resultado mixto

La suite automatizada pasa, pero **la creación completa de una página nueva no
queda aprobada**: dos ejecuciones reales agotaron sus plazos. No se aumentaron
los límites para obtener un resultado verde ni se cambió de modelo.

| Comprobación | Resultado |
|---|---|
| Python | 428 aprobadas, 0 fallos |
| Frontend | 45 aprobadas, 0 fallos |
| TypeScript y build | Aprobados |
| Rechazos HTTP reales | 9/9 aprobados: sesión, origen, ruta y entradas |
| MCP y SQL sin modelo | 34 herramientas anunciadas; contexto y tiros correctos en 1,494 s |
| Crear una página nueva, intento 1 | Falló tras 39,240 s: DATA_EVIDENCE_UNAVAILABLE; Data devolvió DEADLINE_EXCEEDED |
| Crear una página nueva, intento 2 | Falló tras 110,014 s: CHAT_DEADLINE_EXCEEDED; Data sí había completado las dos consultas |
| Editar el informe de QA existente | Aprobado en 15,05 s; mismo informe, dos bloques conservados y análisis reutilizado |
| Pedir xG de Metrica | Aprobado en 12,01 s; aclaración y ningún xG inventado |
| Interfaz | Movimiento del chat, tamaños por teclado, reset, borrador conservado, Escape/foco móvil y navegación al gráfico comprobados |

En el partido sintético 900001, los 23 eventos suman **10 tiros a puerta, 3 goles y
1,6903801272059698 de xG**. La suma evento a evento coincide con el resumen de la
API. Se verificaron 26 hechos del análisis del informe editado contra las fuentes
incluidas en su HTML. El xG sigue identificado como sintético ilustrativo.

La prueba directa de MCP/SQL pasó y el segundo intento completó Data. Esto acota
el problema a los plazos de la cadena agéntica observada; estas pruebas no aíslan
por completo qué inferencia agotó el plazo total ni acreditan una latencia estable.
No se puede prometer creación en menos de un minuto.

## Solicitudes y evidencia

Las solicitudes exactas y los estados completos están en:

- `.temp/workspace-qa-current/create.request.json` y `create.json`: primer fallo.
- `.temp/workspace-qa-current-retry/create.request.json` y `create.json`: reintento.
- `.temp/workspace-qa-current/modify-existing.request.json`, `modify-existing.json`
  y `modify-existing.html`: edición aprobada.
- `.temp/workspace-qa-current/missing-xg.request.json` y `missing-xg.json`:
  aclaración aprobada.
- `.temp/workspace-qa-current/negative-cases.json` y `transport.json`:
  comprobaciones HTTP/MCP.
- `docs/workspace-qa-latest.json`: resultados estructurados, tiempos y huella HTML.

Los estados conservan delegaciones, herramientas, argumentos y hashes de los
prompts. Los prompts editables son `prompts/interpreter.md`, `data_agent.md`,
`sports_analyst.md` e `insights_agent.md`.
No se guardaron cookies ni claves; la credencial configurada se buscó en memoria
contra las salidas guardadas y el bundle sin encontrarla.

Alcance: pruebas reales con Beam Free Go, dos consultas MCP/SQL y los escenarios
indicados. **No equivale a validar las 34 operaciones de nube ni todo el corpus.**
