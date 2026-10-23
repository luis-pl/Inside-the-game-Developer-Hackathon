# Diseño de consultas autorizadas, API, MCP y análisis espacial

Estado: **diseño de referencia**. La API HTTP y el MCP ya están implementados; sus rutas efectivas, definiciones y límites se documentan en [api.md](api.md) y [mcp.md](mcp.md). Este documento conserva las decisiones de diseño iniciales, incluidas rutas que se ajustaron al implementar. Se basa en la carga sintética auditada 3.0.0 y en el [catálogo de capacidades](data-operations-catalog.md). Las 121 capacidades del catálogo no representan 121 herramientas públicas ni 121 funciones implementadas.

La [revisión de cobertura](api-coverage-review.md) identifica tipos, filtros, métricas y consultas todavía no resueltos por esta lista de 21 operaciones. La propuesta no certifica cobertura total del catálogo.

## Decisión principal

El usuario formula preguntas y el agente selecciona operaciones de un catálogo cerrado. El servidor valida sus argumentos y ejecuta una plantilla SQL escrita y revisada por el equipo. Los nombres de tablas, columnas, joins, expresiones y ordenaciones se resuelven exclusivamente en código del servidor.

La API HTTP y el MCP son dos accesos a la misma capa de aplicación. Si se despliegan juntos, comparten funciones internas; si se separan, el MCP llama a la API autenticada. Ninguno mantiene una segunda implementación de las consultas o cálculos.

Recorrido previsto:

1. El intérprete convierte la pregunta en partido/equipo/jugador, ventana y operación reconocida.
2. El agente de datos llama a una tool MCP con argumentos estructurados.
3. El servicio comprueba identidad, alcance, tipos, pertenencia y límites de coste.
4. Una consulta parametrizada obtiene datos desde analytics; cuando corresponde, una función determinista calcula el resultado espacial.
5. El dashboard recibe datos estructurados y el analista recibe métricas, contexto y referencias a la evidencia. Su salida narrativa no ejecuta consultas nuevas por sí sola.

Las herramientas MCP declaran inputSchema y outputSchema. Esa descripción ayuda al modelo, pero la validación efectiva ocurre en el servidor. Las anotaciones de sólo lectura tampoco sustituyen permisos. Referencia: [especificación oficial de tools MCP](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).

## Qué puede elegir el agente

Se permiten IDs existentes, ventanas temporales, resultados/tipos de acción, vistas de respuesta y perfiles de cálculo pertenecientes a enumeraciones cerradas. Las entidades elegidas deben pertenecer al partido y al alcance autorizado.

Por ejemplo, get_shots permite outcome=all/on_target/goal/saved/blocked/off_target y view=events/summary/map/timeline. Cada combinación admitida se resuelve con código y plantillas registradas. Cambiar de summary a map cambia una representación prevista por el equipo; no acepta una proyección SQL inventada por el cliente.

No se admiten sql, where, select, joins, table, column, order_by libre, JSONPath libre, expresiones de métricas, fórmulas, Python, funciones aportadas por el cliente ni instrucciones de ejecutar herramientas arbitrarias. Las propiedades desconocidas se rechazan, incluidas las de objetos anidados. No hay endpoint execute_query ni una tool de SQL genérico.

Las agrupaciones, cuando una operación las admite, son opciones como team/player/time_bin; el servidor las traduce a variantes fijas. Los valores se envían como parámetros SQL. Una lista permitida de nombres no reemplaza la parametrización de los valores.

## Operaciones de datos propuestas

Las rutas son parte del diseño; no están publicadas. Todos los accesos a datos de partido usan vistas analytics de partidos publicados y devuelven procedencia sintética.

| Tool MCP | Acceso HTTP propuesto | Parámetros específicos y resultado |
|---|---|---|
| describe_dataset | GET /api/dataset | Cobertura, unidades, perfiles permitidos y escenarios presentes/ausentes; no un explorador SQL |
| find_entities | GET /api/entities | kind=team/player, nombre de hasta 80 caracteres y match_id opcional; candidatos con ID, sin escoger un nombre ambiguo automáticamente |
| list_matches | GET /api/matches | Equipo, rival, fechas y página; lista de partidos disponibles |
| get_match_context | GET /api/matches/{match_id} | Ficha, equipos, marcador, alineaciones, presencia, formación y run disponible |
| get_team_summary | GET /api/teams/{team_id}/summary | match_ids, profile_id y scope; resultados y métricas del equipo |
| get_player_summary | GET /api/players/{player_id}/summary | match_ids, profile_id y scope; métricas con minutos efectivos |
| get_shots | GET /api/matches/{match_id}/shots | Equipo/jugador, scope, outcome y view; tiros, finales, xG y pases clave |
| get_passes | GET /api/matches/{match_id}/passes | Equipo/jugador, scope, outcome, height, restart, tagged y view; acierto, extremos y receptores |
| get_defensive_actions | GET /api/matches/{match_id}/defensive-actions | kind=pressure/tackle/interception/aerial_duel/clearance/block/recovery, outcome y view |
| get_ball_actions | GET /api/matches/{match_id}/ball-actions | kind=dribble/carry/receipt/miscontrol/dispossessed, outcome y view |
| get_discipline | GET /api/matches/{match_id}/discipline | Faltas y tarjetas, con relación entre perspectivas |
| get_substitutions | GET /api/matches/{match_id}/substitutions | Saliente, entrante, motivo e intervalos de participación |
| get_possessions | GET /api/matches/{match_id}/possessions | Secuencias registradas, participantes, pases, tiros y xG; no porcentaje temporal exacto |
| get_tracking_frame | GET /api/matches/{match_id}/tracking/frame | run_id, period y time_ms; jugadores activos identificados y balón |
| get_tracking_window | GET /api/matches/{match_id}/tracking/window | run_id, ventana, stride_s y equipo/jugador opcionales; reproducción temporal acotada |
| get_event_context | GET /api/events/{event_id}/context | Ventanas anterior/posterior acotadas, relaciones, tracking y capturas disponibles |
| get_heatmap | GET /api/matches/{match_id}/heatmap | Equipo/jugador, scope, mode=event_count/occupancy_seconds, tipo de acción y grid_id |
| get_movement_summary | GET /api/matches/{match_id}/movement | Equipo/jugador y scope; minutos, distancia y velocidades muestreadas |
| get_metric_series | GET /api/matches/{match_id}/metric-series | profile_id, equipo/jugador, scope y bin_s de una lista cerrada; acumulados y series |
| compare_entities | POST /api/comparisons | Dos equipos o dos jugadores, mismos partidos, scope y profile_id; comparación con denominadores |
| get_set_piece_sequences | GET /api/matches/{match_id}/set-pieces | restart=corner/throw_in/free_kick/goal_kick/kick_off y scope; cadena desde la reanudación y desenlace |

Convenciones de estas operaciones:

- view=events es una lista paginada; summary agrega por equipo o jugador cuando se permita; map conserva coordenadas; timeline usa bins registrados.
- Los IDs del proveedor se traducen a nombres de dominio del servicio. on_target se define con Goal/Saved/Saved to Post; no se confunde con un bloqueo.
- get_defensive_actions(kind=aerial_duel) devuelve una fila por disputa con winner y loser relacionados. Un tackle fallido pertenece al defensor superado; Dispossessed pertenece al portador que pierde el balón.
- Los filtros múltiples sólo se aceptan si están definidos en el contrato concreto: no existe un diccionario filters genérico que admita cualquier campo.
- Los campos de raw_payload completos no se publican. La evidencia utiliza IDs y una selección explícita de atributos deportivos.
- Un endpoint de equipo/jugador puede resumir varios de los diez partidos; las consultas de evento, tracking y topología siempre declaran un partido y una generación concretos.

## Perfiles analíticos cerrados

get_team_summary, get_player_summary, get_metric_series y compare_entities se apoyan en un registro de perfiles, no en fórmulas del usuario. Cada perfil declara métricas, fuentes, filtros compatibles, denominadores y entidades permitidas:

| profile_id | Métricas predeterminadas |
|---|---|
| finishing | Tiros, tiros a puerta, goles, xG, xG/tiro, goles menos xG y proporciones por resultado/cuerpo |
| chance_creation | Pases clave, asistencias de gol y suma del xG de tiros asistidos, identificada como xA de esta definición |
| passing | Intentos/completados, acierto, longitud/progresión, entradas a zonas, centros, cambios de orientación y rendimiento bajo presión |
| defending | Intentos de quite y resultado, intercepciones, duelos aéreos, bloqueos, despejes, recuperaciones, faltas, presiones y contrapresiones |
| ball_progression | Regates/intentos/acierto, conducciones, distancia/progresión y pérdidas por causa, deduplicadas |
| movement | Minutos cubiertos, distancia por muestras consecutivas, velocidad media/máxima y segundos sobre umbrales registrados |
| set_pieces | Frecuencia de reanudaciones y cadenas con pase, tiro y xG posterior |
| possession_sequences | Ataques registrados, participantes, pases, progresión, tiros y xG por secuencia |

Cada perfil tendrá una definición única y explícita antes de codificarse. Por ejemplo, passing no puede aceptar progressive_distance_m arbitrario: el registro fija qué reducción de distancia al gol cuenta como progresión. Los perfiles de forma espacial se definen matemáticamente más abajo. PPDA, ventanas de éxito de presión y tasas condicionadas a posesión no se exponen sin registrar antes su fórmula y cobertura; ninguna de esas decisiones se delega al modelo durante la consulta.

Una reanudación inicia una cadena hasta el siguiente reinicio, cambio de posesión o fin de período, lo que ocurra antes. La asociación con un tiro posterior se conserva como relación de secuencia, sin afirmar causalidad. Las pérdidas simultáneas con varias perspectivas se deduplican por reglas registradas y devuelven los event_ids que sustentan cada episodio.

## Funciones espaciales y topológicas propuestas

Conviene describir qué es geometría, qué es teoría de grafos y qué es homología persistente. Todos los cálculos reciben posiciones activas sincronizadas en metros; el servidor transforma eventos 120×80 al sistema del run. El cliente no aporta nubes de puntos para mezclarlas con evidencia de un partido.

Los perfiles de forma/conectividad usan por defecto los jugadores de campo del equipo elegido. El portero se identifica por el rol activo, no por el dorsal. La cobertura de terreno y los corredores incluyen a los porteros activos y lo indican expresamente.

| Función / tool | Método fijado | Salida e interpretación |
|---|---|---|
| get_team_shape | Geometría del equipo de campo | Centroide, ancho, largo, radio de giro, área y perímetro de envolvente: extensión y dispersión del bloque |
| get_proximity_connectivity | Grafo no dirigido con aristas a distancia ≤ε; ε permitido en 5/10/15/20 m | Componentes, aislados, grados, componente mayor y radio crítico de conexión: proximidad y fragmentación geométrica |
| get_space_coverage | Voronoi de ambos equipos activos, recortado al campo | Polígonos y área por jugador/equipo: territorio asignado por distancia, sin probabilidad de llegar antes |
| get_passing_network | Grafo dirigido de pases completados dentro de la ventana | Nodos/participación, conteos por arista, fuerza, densidad y centralidades: circulación observada |
| get_pass_corridor | Distancia de rivales al segmento de un pase raso registrado | Rival más cercano, distancia, proyección y candidatos dentro del corredor de 1,5 m; obstrucción geométrica descriptiva |
| get_line_breaks | Cruces de planos longitudinales de roles al salir un pase completado | Pases que cruzan la línea de referencia, rivales superados longitudinalmente y evidencia del frame inicial |
| get_persistent_structure | Vietoris–Rips sobre distancias; homología H0/H1 | Diagramas nacimiento/muerte y Betti por escala: estructura topológica abstracta, con límites de interpretación |
| get_node_removal_robustness | Retirar cada nodo del grafo de proximidad fijo | Cambio de componentes y proporción de componente mayor: dependencia matemática de un nodo |
| get_defensive_profile | Composición fija de forma, conectividad y contexto rival | Perfil explicable por evidencia; sin una puntuación universal de impenetrabilidad |

Rutas propuestas: POST /api/matches/{match_id}/spatial/{analysis_name}, con analysis_name perteneciente exactamente a las nueve funciones de la tabla. Cada nombre tiene un esquema de entrada propio; no es un ejecutor de nombres de funciones de Python.

### Forma, conectividad y separación crítica

Para puntos p_i=(x_i,y_i): centroide c=media(p_i), ancho=max(y)-min(y), largo=max(x)-min(x) y radio de giro=sqrt(media(||p_i-c||²)). La envolvente requiere al menos tres ubicaciones no colineales para un polígono; en un caso degenerado se devuelve esa condición y área cero, conservando la validez de otras métricas.

El grafo usa la misma distancia euclídea en metros para todos sus nodos. El radio crítico de conexión es el mayor peso del árbol de expansión mínima del grafo completo de distancias. Es la menor ε que conecta todos los puntos con la convención ≤ε, no un pasillo libre, una distancia de presión ni un índice deportivo validado. Con menos de dos ubicaciones válidas se devuelve condición insuficiente. Los duplicados se tratan explícitamente como distancias cero, sin perder las identidades originales.

Referencia matemática: [árbol de expansión mínima en SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.csgraph.minimum_spanning_tree.html).

### Cobertura y corredores

Voronoi se calcula sobre los dos equipos presentes en el mismo frame, incluidos porteros, y se recorta al rectángulo del campo. Las celdas infinitas o degeneradas necesitan tratamiento determinista. Una posición duplicada no se resuelve añadiendo ruido silencioso: se informa como asignación ambigua o se comparte la región con una regla documentada. Las áreas deben cubrir el campo sin solapamientos internos. Referencia: [Voronoi en SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.Voronoi.html).

Para un pase raso con origen a y destino b, cada rival q se proyecta con t=((q-a)·(b-a))/||b-a||². Se considera rival situado entre extremos si 0<t<1; su distancia perpendicular se compara con 1,5 m. Se usan las posiciones rivales en el instante de salida y el destino del pase registrado. Es retrospectivo y estático: no modela aceleraciones, tiempo de vuelo, intención, velocidad de reacción ni capacidad real de interceptar. Para pases elevados esta operación devuelve UNSUPPORTED_GEOMETRY, en vez de aplicar el mismo corredor 2D.

### Líneas y circulación

La referencia longitudinal de cada línea es la mediana x de sus integrantes por rol activo en el frame de salida. Los grupos del perfil cubren defensa, mediocampo y ataque según los IDs de posiciones de la alineación. Se orienta el eje x al equipo que pasa. Un cruce requiere x_origen < x_línea−1 m y x_final > x_línea+1 m; se informa qué línea cruzó y qué jugadores definieron su referencia. Se requiere al menos dos integrantes válidos en la línea. El cálculo mide el cruce respecto a su posición inicial, no una línea inmóvil durante todo el vuelo ni una superioridad táctica demostrada.

En la red de pases, un nodo representa a un jugador activo en algún intervalo de la ventana, incluso si no pasó ni recibió; con sustituciones puede haber más de once nodos en el agregado. El peso es cantidad de pases completados; si se calcula intermediación ponderada, el coste de una arista es 1/conteo. La dirección, la ponderación y el tratamiento de nodos aislados se devuelven como metadata. La red agregada no es una formación simultánea.

### Homología persistente

El perfil rips_h0_h1 fija distancias euclídeas, coeficientes en F2, aristas por distancia ≤ε y símplices hasta dimensión 2, necesaria para rellenar triángulos al calcular H1. El máximo de filtración propuesto es 40 m; las escalas de consulta Betti son 5, 10, 15 y 20 m. No se permite cambiar complejo, métrica, dimensión o coeficientes desde el cliente.

H0 describe componentes a distintas escalas; H1 describe ciclos no rellenados en ese complejo. Las features que sobreviven al corte se marcan como censuradas: death=null no se convierte en cero ni en una vida infinita demostrada sobre toda la filtración. Las persistencias censuradas no se ordenan como si su duración completa fuera conocida.

Un ciclo del grafo de proximidad puede quedar rellenado por un triángulo en Rips. Tampoco se deduce directamente un polígono o un pasillo táctico de una barra H1: una visualización de polígonos/espacios requiere otro algoritmo geométrico. La escala de filtración no es tiempo de partido y las barras entre frames no se identifican automáticamente como el mismo hueco que se mueve. Referencia: [definición y convenciones de Rips en GUDHI](https://gudhi.inria.fr/python/latest/rips_complex_user.html).

### Perfil defensivo y «qué tan impenetrable»

El perfil propuesto reúne:

- Ancho, largo, área y dispersión del equipo de campo.
- Componentes a 15 m y radio crítico de conexión.
- Rivales dentro de la envolvente, distancias a rivales y balón, con cohortes explícitas.
- Corredores de pases rasos rivales y cruces de líneas de referencia.
- Tiros y xG concedidos en el intervalo solicitado, con sus IDs y la procedencia sintética del xG.

Para llamar defensivo a un snapshot, se exige como ancla un pase o tiro del adversario del equipo analizado. En un intervalo, el perfil predeterminado muestrea esas anclas y reporta su cantidad y distribución temporal. No etiqueta todos los segundos como fase defensiva por propagar sin límite la última posesión. Las ventanas de tracking alrededor de una acción son contexto; fuera del ancla, la fase puede ser desconocida.

El resultado es un conjunto de indicadores con evidencia para el analista y el dashboard. Una defensa compacta puede conceder ocasiones, y un hueco topológico puede no ser aprovechable; el análisis debe conservar ese contexto. Un score compuesto exigiría pesos, dirección de cada métrica y validación que aún no existen. La entrega puede mostrar el perfil sin inventar una probabilidad de penetración.

## Contrato temporal y límites propuestos

Estos límites son decisiones de diseño para la demo; deberán fijarse en configuración del servidor y comprobarse al implementar. No son capacidades actuales de un servidor ya desplegado.

| Aspecto | Regla propuesta |
|---|---|
| scope de informes | Objeto cerrado: match, period o window; window exige período y start_ms/end_ms |
| Ventanas | Intervalos [start_ms,end_ms), sin cruzar períodos; las muestras finales pueden pedirse como snapshot, pero no suman tiempo |
| Run | Elegir el único run publicado disponible o exigir run_id si hay varios; devolver siempre el run resuelto |
| Tiempo observado | La carga tiene 1 Hz; snapshots requieren tiempos muestreados, sin interpolación silenciosa |
| Listas de eventos | 100 filas por defecto, máximo 200; cursor opaco y orden estable por período/reloj/event_index/ID |
| Tracking sin agregar | Máximo 120 s por llamada, stride_s en 1/2/5, hasta 22 jugadores y balón por frame |
| Contexto de evento | Antes/después en 0/5/10/15 s, recortado al período; intervalos de presencia preservados |
| Informes agregados | Partido completo permitido; máximo los diez partidos disponibles en resúmenes/comparaciones |
| Heatmaps | grid_id=5m/10m; mode=event_count/occupancy_seconds; equipo/jugador obligatorio |
| Series | bin_s=60/300/900; bins anclados al inicio de período y recortados al scope |
| Topología pesada | Un snapshot o hasta 60 snapshots por solicitud, selección temporal determinista; sin recortar cobertura silenciosamente |
| Perfil defensivo agregado | Hasta 1.000 anclas de pase/tiro rival por partido; si supera el límite, solicitar una ventana menor |
| Comparaciones | Dos entidades del mismo tipo y perfil compatible, con la misma ventana y denominadores |
| Coste | SQL con timeout de 15 s y presupuesto total por solicitud de 30 s; cancelación al desconectarse el cliente |
| Concurrencia inicial | Dos cálculos espaciales simultáneos por identidad y cola global acotada; sin reintentos ilimitados |
| Respuesta | Máximo 1 MiB y contadores de cobertura; rechazar/dividir una solicitud excesiva, sin truncar estadísticas |

Se puede precalcular geometría y topología por frame/ventana para la demo y cachear resultados. La clave debe incluir una revisión de datos inmutable, run_id, operación, perfil/método, parámetros normalizados y alcance de acceso. generator_version por sí solo no identifica una reparación administrativa dentro de la misma versión. Ese identificador de revisión se debe introducir como metadata del servicio/manifiesto; no se presume que ya exista como columna de la base.

La identidad de la aplicación usa lectura de analytics, sin credenciales del administrador ni permisos para alterar datos o publicar partidos. Los usuarios acceden a la API/MCP autenticados; no reciben credenciales SQL. Un token válido no da acceso a operaciones fuera del registro. Los límites se aplican también en MCP y en llamadas internas del agente.

## Ejemplo de contrato para tiros

Pregunta: «¿Cuántos tiros a puerta hizo el equipo 1 en el partido 900001 y dónde fueron?».

Tool elegida y argumentos permitidos:

```json
{
  "tool": "get_shots",
  "arguments": {
    "match_id": 900001,
    "team_id": 1,
    "scope": {"kind": "match"},
    "outcome": "on_target",
    "view": "map"
  }
}
```

La API recibe los mismos campos en su ruta/argumentos. Internamente selecciona la plantilla registrada shots_on_target_map y enlaza @match_id/@team_id. El cliente nunca envía la plantilla, su ruta de archivo ni texto SQL. La respuesta conserva un summary con el total exacto y una página de items con event_id, período/reloj, jugador, resultado, coordenadas y xG; si hay más items, se informa next_cursor.

Forma de respuesta propuesta, con campos a completar por el servidor:

```text
operation_id, method_id, request_id
scope: match_id, team_id, player_id, period/window cuando aplique
data: summary + items/series/geometries según el view
provenance: is_synthetic, generator_version, dataset_revision, run_id
coordinates: fixed_pitch_m o acting_team_120x80, orientación y dimensiones
coverage: expected_samples, valid_samples, coverage_ratio, phase_evidence
pagination: next_cursor cuando corresponda
warnings: ausencias o supuestos concretos
```

En respuestas de varios partidos, provenance y coverage se conservan por partido/run, además de cualquier resumen global. Una agregación no oculta que compara generaciones, ventanas o coberturas diferentes.

## Errores y criterios de aceptación

El contrato distingue INVALID_ARGUMENT, ENTITY_NOT_IN_MATCH, RUN_AMBIGUOUS, WINDOW_TOO_LARGE, UNSUPPORTED_METRIC, UNSUPPORTED_GEOMETRY, INSUFFICIENT_COVERAGE, RATE_LIMITED y TEMPORARILY_UNAVAILABLE. Un cero válido se devuelve con cobertura; la ausencia de un escenario o campo no se sustituye por cero. Los errores externos no incluyen SQL, tokens ni trazas internas.

La implementación se considerará conforme cuando:

1. SQL, propiedades desconocidas y nombres de función no registrados se rechacen tanto por HTTP como por MCP.
2. Ambos accesos den el mismo resultado para los mismos argumentos y revisión de datos.
3. Los totales y páginas de tiros, duelos, recepciones, faltas y sustituciones eviten duplicar perspectivas y respeten minutos efectivos.
4. Las coordenadas y direcciones coincidan entre eventos y tracking; ninguna distancia combine 120×80 con metros sin transformación.
5. Conectividad y MST coincidan en el umbral crítico; un triángulo completo tenga H1=0; los resultados no dependan del orden de los jugadores y sean invariantes a traslaciones/rotaciones para métricas de distancia.
6. Voronoi recortado cubra el área del campo; datos degenerados y cobertura insuficiente produzcan resultados explícitos y reproducibles.
7. Las comparaciones indiquen tamaño de muestra, método, estado sintético y los límites de fase/conocimiento.

La guía utilizada para el diseño de validación, consultas parametrizadas, permisos y límites es [api-security-best-practices](<C:/Users/USUARIO/.agents/skills/api-security-best-practices/SKILL.md>). Su uso aquí produce una especificación; no crea identidades, infraestructura, endpoints ni permisos nuevos.
