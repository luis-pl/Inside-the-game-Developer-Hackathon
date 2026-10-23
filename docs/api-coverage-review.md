# Revisión de cobertura del diseño API/MCP

Estado: revisión de diseño, sin implementación ni pruebas de endpoints. Se contrastaron las 21 operaciones de datos y las nueve funciones espaciales de [la propuesta](api-mcp-topology-design.md) con las 121 capacidades del [catálogo](data-operations-catalog.md).

Actualización: la API ya implementa las 25 operaciones de datos y nueve espaciales. Esta revisión conserva los huecos detectados antes de construirla; el comportamiento efectivo y las exclusiones están en [api.md](api.md) y los resultados de integración en [api-verification.json](api-verification.json). Esto no convierte en disponibles los modelos o escenarios ausentes descritos más abajo.

**La lista de 21 operaciones, tal como está descrita, no certifica cobertura completa.** Agrupa las familias principales, pero algunos tipos, filtros, resultados y cálculos todavía no tienen contrato. La cobertura depende de las variantes aprobadas y sus consultas, no de la cantidad de endpoints.

## Huecos concretos y resolución propuesta

| Necesidad del catálogo | Situación en las 21 operaciones | Resolución acotada |
|---|---|---|
| Cronología transversal de todos los eventos registrados | Hay listas especializadas, sin operación transversal | Añadir get_events con tipos/zonas/resultados enumerados, orden temporal estable y páginas |
| Secuencias como A-B-A, acción tras regate, pérdida seguida de tiro y recuperación tras presión | Posesiones y contexto local no definen todos esos patrones ni sus denominadores | Añadir get_sequences con pattern_id registrado y ventanas fijadas por cada patrón; sin lenguaje de patrones libre |
| Tiempo en zonas, entradas/salidas y acciones producidas allí | Un mapa de calor no define todas las agregaciones por zona | Añadir get_zone_summary con zone_id y report_id de un registro cerrado y orientación explícita |
| Rankings de todos los jugadores/equipos disponibles | Resúmenes individuales y comparación de dos entidades no ofrecen por sí solos un ranking | Añadir get_rankings con métricas compatibles con cada perfil, minutos mínimos y desempate definidos |
| 50/50 | No aparece en el enum de get_defensive_actions | Agregar kind=fifty_fifty con desenlaces canónicos y perspectivas relacionadas |
| Portería | Shot Saved se puede contextualizar, pero no hay contrato explícito de actividad del portero | Agregar kind=goalkeeper en acciones y perfil goalkeeping en resúmenes/series; deduplicar tiro Saved y evento de parada |
| Antes/después de una sustitución o comparación entre tiempos | compare_entities exige dos entidades y la misma ventana | Agregar mode=entities/windows; windows admite dos scopes del mismo partido con cobertura y duración explícitas |
| Ganando/empatando/perdiendo, local/visitante, zonas y condición de presión | No todos los filtros están declarados en cada contrato | Registrar por operación enums compatibles, incluido score_state previo a cada acción y zone_id; rechazar combinaciones no soportadas |
| PPDA, efecto posterior a presión y demora hasta recuperar | La propuesta deja pendiente su fórmula | Registrar los perfiles y sus fórmulas, ventanas, acciones incluidas y segundos sin clasificar antes de exponerlos |
| Posesión temporal e instantes entre muestras | No forman parte del contrato observado | Mantener fuera de las respuestas exactas; admitirlos sólo con perfiles de estimación explícitos, si se decide incluirlos |
| Matriz de distancias, triangulación y superioridades locales | Las nueve funciones espaciales no especifican todas esas salidas | Declarar variantes registradas matrix/graph, triangulación y conteos locales en los contratos espaciales correspondientes |
| Corredores de tiro | La función propuesta sólo trata pases rasos | Definir un cálculo geométrico para tiros con sus límites 2D/3D o señalarlo expresamente fuera del alcance; no reutilizar sin explicación el de pases |

Las cuatro operaciones nuevas propuestas llevarían el conjunto de datos a **25 operaciones**, además de las nueve de análisis espacial. Ese número describe la organización sugerida; no demuestra por sí mismo que todas las capacidades estén implementadas.

## Límites que una operación adicional no resuelve

- La carga no contiene casos anotados de penalti, expulsión, fuera de juego, lesión ni prórroga. Un endpoint no crea ejemplos ni certifica esos escenarios.
- xT, OBV, EPV, post-shot xG y pitch control requieren modelos y parámetros adicionales. No se obtienen simplemente exponiendo coordenadas.
- Una puntuación de impenetrabilidad necesita definición y validación. El perfil defensivo explicable propuesto reúne indicadores, sin afirmar esa puntuación.
- Un porcentaje temporal de posesión requiere inferir el dueño del balón; no está almacenado por frame. El tiempo entre primer y último evento de una posesión tampoco certifica su duración exacta.

## Condición para cerrar el alcance

Cada capacidad incluida en la entrega debe tener una fila de trazabilidad con:

1. Pregunta de usuario y capability_id.
2. Operación y variante/report_id autorizados.
3. Plantilla SQL y, si corresponde, función matemática.
4. Parámetros, filtros compatibles, unidades y denominador.
5. Respuesta esperada y tratamiento de falta de cobertura.
6. Ejemplo ejecutado contra los datos sintéticos y validación del resultado.

Las capacidades excluidas deben quedar explícitas. Mientras falten fórmulas, contratos y esas comprobaciones, el diseño se mantiene como propuesta. Esta revisión identifica huecos; no afirma que se hayan implementado las cuatro operaciones adicionales o completado las variantes restantes.
