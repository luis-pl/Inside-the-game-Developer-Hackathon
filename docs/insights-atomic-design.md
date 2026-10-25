# Propuesta: insights paramétricos con diseño atómico

Estado: **diseño aprobado**. Las veinte familias originales están implementadas
y ampliadas a treinta. Estado, ejecución y MCP en [insights.md](insights.md);
fuentes y adaptaciones en [insights-research.md](insights-research.md).
El resto conserva la propuesta funcional que originó la implementación.

## Resultado que buscamos

El agente de insights compone un informe de fútbol a partir de evidencia obtenida
por el agente de datos. Selecciona piezas de un registro y completa parámetros.
Un renderer determinista produce un HTML autocontenido. El analista deportivo
conserva la responsabilidad del texto interpretativo.

Se propone usar el módulo existente `dashboard_builder.py` para ese agente de
insights; no hace falta crear un quinto agente con responsabilidades duplicadas.

La unidad de selección del LLM será un organismo o una receta de insight. Átomos
y moléculas se reutilizan dentro de las recetas: pedir al modelo que coloque cada
etiqueta, punto o línea haría la composición lenta y frágil.

La jerarquía sigue [Atomic Design de Brad Frost](https://atomicdesign.bradfrost.com/chapter-2/):
átomos, moléculas, organismos, templates y páginas. Un template describe la
estructura; una página es su instancia con contenido y evidencia concretos.

## Las piezas de Lego

| Nivel | Piezas propuestas | Responsabilidad |
|---|---|---|
| Fundamentos | Tipografía, colores por entidad, escala espacial/temporal, espaciado, unidades | Reglas compartidas; no son una sexta clase de insight |
| Átomos | Texto, número, unidad, etiqueta de entidad, punto de evento, vector, celda térmica, marca de eje, muestra de leyenda, estado, enlace a evidencia | Una función visual elemental |
| Moléculas | Lectura de métrica, fila comparativa, evento con tooltip, entrada de cronología, leyenda, lectura de cobertura, aviso de procedencia | Pequeñas agrupaciones con significado reutilizable |
| Organismos | Cabecera de partido, franja de métricas, mapa de campo, mapa térmico, serie temporal, cronología, red, tabla ordenada, comparación, secuencia, replay, panel topológico, pie de evidencia | Secciones completas alimentadas por contratos de datos |
| Templates | Resumen de partido, ficha de jugador, comparación, episodio táctico, informe libre con slots tipados | Distribución y orden de los organismos, sin datos concretos |
| Páginas | Template + bloques + parámetros + evidencia + notas del analista, si existen | HTML final que se abre sin servidor ni conexión |

El sistema amplía el lenguaje visual ya presente en el visor: fondo claro,
tipografía legible, verde oscuro y colores estables por equipo. Esta propuesta
no fija un rediseño ni sustituye la pantalla actual. Los futuros componentes deben
tener tabla o texto alternativo, navegación por teclado y estados legibles sin
depender sólo del color.

## Catálogo de 20 familias

Son familias, no veinte páginas rígidas. Las variantes cambian datos, capas,
filtros y disposición reutilizando los mismos organismos.

| # | ID / insight | Pregunta que ayuda a responder | Consultas existentes | Composición principal |
|---|---|---|---|---|
| 1 | `shot_map` — Mapa de tiros | ¿Cuántos tiros hubo, cuándo y desde dónde? | `get_shots` | pitch_map |
| 2 | `xg_story` — Evolución y distribución del xG | ¿Dónde y cuándo se acumuló el xG disponible? | `get_shots`, `get_metric_series` | time_series |
| 3 | `match_timeline` — Cronología del partido | ¿Cuándo se concentraron las acciones y qué cambios se registraron? | `get_metric_series`, `get_substitutions`, `get_discipline`, `get_events` | timeline |
| 4 | `pass_map` — Mapa de pases | ¿Cómo circuló el balón y hacia dónde? | `get_passes` | pitch_map |
| 5 | `passing_network` — Red de conexiones | ¿Qué parejas intercambiaron más pases completados? | `get_passing_network` | network |
| 6 | `sequence_explorer` — Secuencias y balón parado | ¿Cómo fueron las cadenas de acciones registradas? | `get_possessions`, `get_sequences`, `get_set_piece_sequences` | sequence |
| 7 | `defensive_actions` — Acciones defensivas y duelos | ¿Dónde y cuándo se anotaron quites, intercepciones o duelos ganados? | `get_defensive_actions` | pitch_map |
| 8 | `pressure_recovery` — Presión y recuperación | ¿Qué presiones registradas terminaron en recuperación? | `get_defensive_actions`, `get_sequences` | sequence |
| 9 | `ball_progression` — Regates y conducciones | ¿Dónde hubo desequilibrio o avance mediante acciones con balón? | `get_ball_actions` | pitch_map |
| 10 | `occupation_heatmap` — Mapa de ocupación | ¿Qué zonas ocupó el jugador o el equipo? | `get_heatmap` | heatmap |
| 11 | `movement_profile` — Perfil de movimiento | ¿Qué distancia y movimiento se observaron? | `get_movement_summary` | comparison |
| 12 | `play_replay` — Reproducción y contexto de jugada | ¿Dónde estaban los jugadores alrededor de una acción? | `get_tracking_frame`, `get_tracking_window`, `get_event_context` | replay |
| 13 | `zone_presence` — Presencia y actividad por zonas | ¿En qué zonas se observaron jugadores y acciones? | `get_zone_summary`, `get_heatmap` | zone_summary |
| 14 | `team_shape` — Forma del bloque | ¿Qué anchura, profundidad y dispersión tenía el equipo? | `get_team_shape` | topology |
| 15 | `proximity_network` — Conectividad por proximidad | ¿Cómo se conectaban los jugadores a una distancia dada? | `get_proximity_connectivity` | network |
| 16 | `space_partition` — Partición espacial Voronoi | ¿Cómo se repartía geométricamente el espacio? | `get_space_coverage` | topology |
| 17 | `persistent_structure` — Persistencia de la estructura | ¿Qué componentes y ciclos aparecen según la escala? | `get_persistent_structure` | topology |
| 18 | `node_robustness` — Sensibilidad al retirar jugadores | ¿Qué jugadores alteran más la conectividad del grafo al retirarlos? | `get_node_removal_robustness` | topology |
| 19 | `entity_comparison` — Comparación de jugadores y equipos | ¿En qué métricas comparables se diferencian? | `compare_entities`, `get_player_summary`, `get_team_summary`, `get_rankings` | comparison |
| 20 | `defensive_geometry` — Corredores y rupturas defensivas | ¿Qué evidencia geométrica hay alrededor de pases o tiros rivales? | `get_pass_corridor`, `get_line_breaks`, `get_defensive_profile` | topology |

Los requisitos y las variantes de cada familia están en
[el catálogo estructurado](insights-catalog.proposal.json). Su lista de parámetros
es orientativa por familia: no significa que todas sus tools acepten esos campos.

### Disponibilidad que debe ver el usuario

- xG: disponible en el historial sintético, identificado como ilustrativo. En los
  partidos reales actuales se muestra «no disponible»; no se simula ni se cambia
  silenciosamente de partido.
- Resultados de tiro: SkillCorner no permite clasificar los tiros individuales
  como gol/parada/fuera. Puede mostrar sus ubicaciones con resultado desconocido.
- Presión, regates, duelos, disciplina, balón parado y roles: comprobar anotaciones
  por partido. Existir una operación no acredita cobertura de esa fuente.
- Metrica: sus pases identificados son completados; no se deriva una tasa de
  acierto total suponiendo que constituyen todos los intentos.
- Corredores: sólo pases rasos anotados y tracking anclado. Metrica no aporta altura
  del pase; no se habilita esta variante suponiendo que todos son rasos.
- Hodge: se puede incorporar como variante de red reutilizando los cálculos del
  frontend. No existe una tool MCP de Hodge hoy; falta un adaptador compartido.
- Voronoi, persistencia y retirada de nodos se presentan con su interpretación
  geométrica. No acreditan control probabilístico ni calidad táctica calibrada.
- Los alias reales son por partido: una comparación entre encuentros no puede
  asumir identidad del mismo jugador por compartir dorsal o etiqueta.

## Qué significa paramétrico

Hay tres contratos separados; no una bolsa de opciones enviada a cualquier tool.

1. **Consulta:** identificadores, alcance y filtros aceptados por cada operación.
   El adaptador los valida con los contratos actuales del MCP de datos.
2. **Datos normalizados:** evidencia original, unidades, sistemas de coordenadas,
   cobertura y método, adaptados a una familia visual mediante código conocido.
3. **Presentación:** título, leyenda, capas disponibles, densidad, colores por
   entidad y slots de layout. No modifica el significado o el alcance de los datos.

Ejemplos de parámetros concretos:

| Familia | Parámetros de consulta / selección | Parámetros de presentación |
|---|---|---|
| Tiros | Partido, equipo/jugador, scope, outcome, body_part | Etiqueta del evento, símbolo por resultado; tamaño por xG sólo si existe |
| Ocupación | Partido, participante, scope, mode, grid_id | Paleta, leyenda, escala compartida al comparar |
| Red de pases | Partido, equipo, scope, view | Etiquetas, grosor por peso; umbral visual con conexiones ocultas declarado |
| Conectividad | Partido, equipo, instante o ventana; epsilon_m de 5/10/15/20 | Componentes, aislados o matriz |
| Comparación | Dos entidades o dos ventanas en compare_entities; resúmenes para más | Barras alineadas, tabla y unidades comunes |
| Replay | Partido, período, intervalo, run, sample_step_ms cuando sea compatible | Reproducir, pausar, buscar, velocidad literal y capas incluidas |

`normalization=per90` sólo se envía a las operaciones que lo admiten, por ejemplo
rankings; no se inventa ese campo para compare_entities. Los perfiles y enums
conservan su lista cerrada.

En operaciones espaciales no se combinan event_id con una selección de instante.
Las ventanas de geometría están limitadas a 60 s; tracking a 120 s por llamada.
Para tracking real a 5 Hz se pide sample_step_ms=200 y se usan tramos pequeños.
La paginación permanece bajo control del ejecutor de datos.

### Contrato visual común propuesto

Cada dataset asociado a un bloque necesita como mínimo:

- IDs de evidencia y de query, operación, método y argumentos ejecutados.
- Entidades, partido/run y scope efectivos; reloj relativo al período.
- Unidad, sistema espacial y orientación; dimensiones del campo cuando proceda.
- Estado: ready, empty_with_coverage, partial, unavailable, incompatible o error.
- Procedencia, cobertura y advertencias originales.
- Datos originales o referencia autorizada a ellos dentro de la misma solicitud.

Ausencia y cero son estados distintos. Las comparaciones usan unidades,
normalización, denominadores y escalas compatibles. Nunca se comparan segundos
de ocupación con número de eventos en la misma escala como si fueran equivalentes.

Los gráficos de eventos pueden usar el sistema 120×80 del equipo actuante; tracking
usa metros con orientación fija. Una superposición exige una transformación
explícita con equipo, período y orientación conocidos. No basta con estirar ejes.

## Composición de una página

Ejemplo ilustrativo de un manifiesto, no de un endpoint ya implementado:

```json
{
  "schema_version": "proposal-1",
  "template_id": "player_dossier",
  "title": "Posicionamiento del jugador seleccionado",
  "blocks": [
    {
      "id": "occupation",
      "insight_id": "occupation_heatmap",
      "slot": "main",
      "bindings": {"heatmap": "e1"},
      "presentation": {"legend": true}
    },
    {
      "id": "movement",
      "insight_id": "movement_profile",
      "slot": "supporting",
      "bindings": {"movement": "e2"},
      "presentation": {"density": "compact"}
    }
  ]
}
```

e1/e2 deben existir en la respuesta de esa solicitud y satisfacer los requisitos
del bloque. El renderer rechaza un ID desconocido, un binding incompatible o un
scope incoherente. No interpreta rutas, expresiones JavaScript, SQL ni componentes
inventados. Las recetas definen bindings y slots permitidos.

Tres páginas posibles usando el mismo catálogo:

- **Informe ofensivo:** mapa de tiros + evolución del xG si existe + pases +
  secuencias. Con la fuente real actual, el bloque de xG conserva el estado ausente.
- **Comparación de jugadores:** ocupación + movimiento + acciones con balón +
  comparación tabular; cada participante conserva su cobertura y minutos.
- **Episodio defensivo:** replay corto + forma + proximidad + Voronoi +
  persistencia/retirada. Cada lectura usa el mismo instante o ventana declarada.

## MCP de composición implementado

El agente obtiene datos del agente de datos mediante el futuro adaptador de
comunicación entre agentes. El agente de datos ya usa su MCP de consultas.
El MCP de insights describe y renderiza piezas, con evidencia aportada por el anfitrión.

| Tool | Función |
|---|---|
| list_insights | Descubrir las 30 familias, variantes y requisitos |
| describe_insight | Obtener esquema de parámetros, bindings, estados y combinaciones admitidas |
| validate_report | Validar manifiesto, evidencia, compatibilidad y presupuesto de tamaño |
| render_insight | Crear una pieza individual a partir de parámetros e IDs de evidencia |
| render_report | Ensamblar el HTML y devolver artefacto, estados por bloque y métricas de tiempo/tamaño |

No hace falta una tool por átomo o por insight. Tampoco debe ejecutarse un nuevo
turno del modelo por componente. El LLM selecciona un conjunto de recetas y ordena
las secciones en uno o pocos turnos; el renderer resuelve la composición atómica.

El agente no vuelve a redactar todos los eventos o frames en JSON: usa IDs de
evidencia. El anfitrión conecta esos IDs con los originales autorizados.
Las cinco tools están implementadas en `inside_game.insights.mcp_server`. La
evidencia autorizada y los recursos HTML viven en la instancia de cada solicitud.
La comunicación A2A y el agente conversacional siguen pendientes; el renderer
y su MCP no dependen de ellos para funcionar. Uso: [insights.md](insights.md).

## HTML autocontenido y objetivo de tiempo

El resultado incluirá CSS, SVG, datos y el JavaScript necesario en un único
archivo. Sin CDN, fuentes remotas, fetch a APIs ni claves de acceso. Filtros,
tooltips y reproducción trabajan sobre los datos incluidos. Los datos se serializan
con escape seguro; nombres y texto no se ejecutan como HTML o scripts.

Se reutilizará un bundle preparado previamente; no ejecutar npm install, build
ni generación de código por cada solicitud. Los adaptadores deterministas podrán
ordenar, normalizar unidades conocidas o acumular métricas aditivas definidas;
no crearán nuevos modelos deportivos. La evidencia original se conserva.

Objetivos de ingeniería **pendientes de benchmark**:

| Tramo | Objetivo propuesto |
|---|---|
| Validar, ensamblar y guardar HTML con evidencia ya disponible | p95 menor de 2 s para informe estático estándar |
| Selección de recetas + composición, con datos listos | Buscar 10–15 s |
| Solicitud completa incluyendo modelo, red y consultas | Buscar menos de 60 s; no está garantizado hoy |

El agente de datos actual tiene deadline de 240 s. Por tanto, no se puede prometer
menos de un minuto extremo a extremo sin introducir presupuesto de tiempo
compartido, cancelación y salida parcial. Un coordinador futuro podría reservar
el tramo final para renderizar lo ya recuperado, dejando visibles los bloques
pendientes. Hay que medir p50/p95 y separar arranque en frío de ejecución caliente.

Límites iniciales a medir: informes estáticos con 3–6 insights principales; varias
entidades dentro del mismo bloque; replay corto a 5 Hz. Una reproducción de 90
minutos no tiene el mismo presupuesto de transferencia que un mapa de tiros.
No se recortan eventos sin indicarlo ni se inventan frames para acelerar.

## Reutilización del código actual

El visor ya dispone de campo, leyendas, cronología, reproducción, conectividad,
persistencia, retirada y Hodge. Son material para extraer funciones y presentación
puras. Muchos componentes actuales reciben el objeto global Lab y dependen del
estado de la aplicación: no basta con copiarlos en un HTML independiente.

La extracción debe separar datos, cálculos deterministas y presentación. Antes
de usar una pieza en el renderer se verifica que funciona sin el servidor del
visor, maneja ausencia de datos y mantiene método/convenciones originales.

## Validación de la futura implementación

- Contratos con datos vacíos, ceros reales, NULL, huecos y solicitudes parciales.
- Diez partidos reales y escenarios sintéticos, con procedencia visible.
- Escalas, unidades y períodos coherentes; no duplicar agregados de páginas.
- Mismo manifiesto y evidencia producen el mismo contenido y orden.
- HTML abierto sin red, sin credenciales y con datos/textos correctamente escapados.
- Escritorio, móvil, impresión, teclado y alternativa legible al gráfico.
- Tiempo y tamaño medidos por familias de informe; no sólo un ejemplo pequeño.

Fuentes del proyecto: registro actual en src/inside_game/service.py, contratos en
src/inside_game/contracts.py, procedencia en database/azure-sql/README.md y
DATA-QUALITY.md, y componentes/cálculos existentes en frontend/src/.
