# Datos e insights para la entrega de la hackathon

La base permite construir el agente de datos sobre consultas verificables. La revisión encontró que la carga 2.0.0 omitía acciones básicas, aunque sus filas fueran coherentes con las restricciones anteriores. Se reemplazó por una simulación 3.0.0 con cobertura analítica explícita y controles de relaciones, geometría y tiempo. Las implementaciones de agentes, API y MCP siguen reservadas; estos documentos definen qué podrán consultar.

## Evidencia y ubicación

- [Calidad y límites de la carga](../database/azure-sql/DATA-QUALITY.md).
- [Cobertura comprobada en Azure](../database/azure-sql/coverage-cloud-report.json).
- [Auditoría de las filas recuperadas de Azure](../database/azure-sql/realism-cloud-report.json).
- [Perfil de tablas, campos, dominios y valores presentes](data-capabilities-evidence.json).
- [Catálogo completo de operaciones](data-operations-catalog.md) y [su formato JSON](data-operations-catalog.json).
- [Diseño de operaciones autorizadas, API/MCP y funciones topológicas](api-mcp-topology-design.md).
- [Consultas de cobertura y acciones añadidas](../database/azure-sql/queries-coverage.sql) y [consultas de tiros, calor y presión](../database/azure-sql/queries.sql).
- [Pruebas de entradas espaciales calculadas sobre datos de Azure](data-capabilities-proofs.json).

Se conservan 30 tablas y 250 columnas físicas en statsbomb, incluidas las columnas de administración/publicación. analytics expone vistas de partidos publicados. Los eventos con atributos especializados de pase o tiro tienen tablas propias; los demás usan events.details, un objeto JSON consultable con JSON_VALUE/OPENJSON. Por eso una intercepción o un regate no requiere inventar otra tabla para poder analizarse.

## Preguntas que la carga sí permite explorar

| Pregunta | Entradas | Cómo se responde |
|---|---|---|
| ¿Cuántos tiros a puerta, cuándo y desde dónde? | events + event_shots / analytics.shots | Filtrar partido; resultado Goal/Saved/Saved to Post, período y reloj; devolver actor, ubicación y xG |
| ¿Qué ocasiones creó cada jugador? | event_passes + event_shots.key_pass_id | Pases clave, asistencias y suma de xG de tiros asistidos; no contar la relación como otro pase |
| ¿Qué pasó en cada tiro? | shot_freeze_players + frames_360 + event_tracking_links | Situación espacial y ventanas antes/después, con compañeros/rivales, portero y balón |
| ¿Dónde estuvo un jugador y qué zonas ocupó? | tracking_player_positions + tracking_frames | Posición por segundo activo; calor ponderado por duración y separado por período/run |
| ¿Quién ganó quites y dónde? | events/type=Duel, details.duel | Tackle con resultado Won; Lost In Play es el intento fallido del defensor superado, no la desposesión del portador |
| ¿Quién interceptó pases? | events/type=Interception | Actor, resultado, posición y siguiente secuencia de posesión |
| ¿Quién ganó disputas aéreas? | Duel/Aerial Lost + Clearance/aerial_won + event_relations | Relacionar perdedor y ganador; un enfrentamiento, dos perspectivas |
| ¿Qué regates funcionaron? | Dribble + Dribbled Past / Dispossessed | Completos e incompletos por actor, rival, zona y momento; tasa por intento |
| ¿Quién avanzó conduciendo? | Carry/end_location + tracking | Progresión hacia el gol, duración, distancia recorrida y entradas a zonas |
| ¿Quién pierde el balón y cómo? | Miscontrol, Dispossessed, Dribble e incomplete Pass | Clasificar pérdidas con reglas explícitas; agrupar acciones del mismo episodio para evitar duplicados |
| ¿Quién recibió, progresó y conectó el juego? | Pass + Ball Receipt* | Redes emisor-receptor, recepciones, dirección, altura, acierto, zonas y secuencias |
| ¿Cómo rindió bajo presión? | Pressure, under_pressure, counterpress | Comparar resultados de pases y acciones en ventanas; no confundir presión ejercida con recibida |
| ¿Qué hizo la defensa ante un remate? | Block, Shot/Blocked, Goal Keeper | Bloqueador/parada identificados y enlazados, distancias y evolución espacial |
| ¿Qué ocurrió en córners, bandas y faltas? | pass_type + play_pattern | Secuencias, progresión y tiros posteriores; un pase Free Kick no es un tiro libre directo |
| ¿Cómo cambió el partido tras una sustitución? | Substitution + lineup_positions + tracking | Identificar entrante/saliente, minutos y ventanas antes/después; describir asociación, sin atribuir causalidad |
| ¿Cómo cambia el bloque defensivo? | Posiciones simultáneas, roles, dirección y balón | Centroide, ancho, largo, área de envolvente, separaciones y superioridades locales |
| ¿Qué espacios o corredores aparecen? | Distancias y segmentos de pase/tiro | Proximidad y obstrucción geométrica según radios y umbrales publicados |
| ¿Quién corre más y cuándo? | Trayectorias activas y tiempo entre muestras | Distancia y velocidad por diferencias finitas; tasas normalizadas por minutos efectivos |
| ¿Cuánto se juega realmente? | tracking_frames.ball_in_play | Duración de intervalos con balón vivo/parado; los extremos de período no son tiempo extra |
| ¿Cómo se comparan equipos y jugadores? | Datos anteriores con filtros comunes | Mismas ventanas, rivales, estado del marcador, minutos y denominadores |

El catálogo amplía estas preguntas en operaciones reutilizables, con estado observado, calculable, estimado o dependiente de un modelo. Un mismo conjunto de filtros sirve para varias visualizaciones; no se necesita una tool por cada pregunta posible.

## Preguntas que también deben quedar presentes

La cobertura se revisó considerando creación de ocasiones, eficacia de finalización, superficie del remate, balón parado, circulación, progresión por pase y conducción, pérdidas, disputa física, recuperación, presión, portería, disciplina, cambios de personal, ocupación espacial y comparación temporal. Hay cuestiones distintas que no deben confundirse:

- Una mayor área del bloque no demuestra una defensa peor; necesita contexto de balón, rival y fase.
- Muchas presiones no demuestran eficacia: hay que definir el desenlace y la ventana que se atribuye a cada presión.
- Sumar duraciones de dos presiones simultáneas duplica el tiempo de equipo; la unión de intervalos responde otra pregunta.
- La posesión por número de eventos no es posesión por tiempo. No hay dueño del balón almacenado en cada frame: esa clasificación exige un método explícito y segundos sin asignar.
- Un pase recibido seguido de mal control es un pase completado y una pérdida posterior, no un pase incompleto.
- Los tiros concedidos y su xG pueden compararse con compactación y corredores, pero diez partidos sintéticos no prueban una relación causal.
- Un cambio de jugadores con 433 no es evidencia de un cambio de sistema táctico.
- Las acciones ganadas de un duelo y sus perspectivas perdedoras no son enfrentamientos independientes.

## Entradas disponibles para las funciones topológicas

Para cada segundo se puede preparar una nube sincronizada de 22 jugadores activos con IDs, equipo, puesto, coordenadas métricas, balón, período, orientación y estado de juego. Los eventos enlazados permiten elegir episodios de ataque, defensa, pase o tiro y conservar su desenlace. Las sustituciones modifican correctamente los nodos presentes.

Sobre esos datos pueden calcularse matrices de distancias, grafos de proximidad, redes de pases, envolventes, triangulaciones y series de forma. Las pruebas adjuntas ya calculan centroides, extensiones, áreas y redes a partir de filas recuperadas de Azure. Para redes agregadas de todo el partido, pueden aparecer 14 participantes por equipo; en una muestra simultánea hay 11. Una retirada matemática de nodos no equivale a simular el comportamiento real de un equipo tras un cambio.

La función de «impenetrabilidad» todavía necesita una definición: participantes incluidos, escalas métricas, tipo de complejo/grafo, ventana y regla que relaciona el indicador con penetraciones o tiros concedidos. Un ciclo de grafo no equivale automáticamente a un hueco topológico ni a un espacio táctico aprovechable. El dato necesario para experimentar existe; el resultado deportivo no viene predefinido en la base.

En una envolvente 2D de SciPy, volume representa el área y area el perímetro. Las celdas Voronoi deben recortarse al campo; su proximidad no equivale a control probabilístico del terreno. En Rips se deben declarar umbral, dimensión y filtración antes de interpretar persistencia. Referencias: [ConvexHull](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.ConvexHull.html), [Voronoi](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.Voronoi.html) y [GUDHI Rips](https://gudhi.inria.fr/python/latest/rips_complex_user.html).

## Reglas para diseñar las consultas del agente

1. Resolver IDs y comprobar cobertura antes de analizar. Distinguir cero observado, campo sin anotación y escenario ausente.
2. Usar match_id + run_id + período + reloj; ordenar eventos del mismo instante por event_index. La posesión se identifica por match_id + possession.
3. Convertir a metros y orientar al equipo elegido antes de mezclar eventos 120×80 con tracking fijo 105×68. No mezclar lados del campo al cambiar de tiempo.
4. Aplicar intervalos de actividad, posiciones válidas y duración real de muestras. No atravesar huecos ni el descanso al calcular distancias o calor.
5. Definir denominadores, unión de intervalos, deduplicación y filtros de resultado. Dividir por cero devuelve NULL con explicación.
6. Devolver is_synthetic, versión, ventana, unidades, método, cobertura y advertencias concretas junto a cada resultado.
7. Acotar el tamaño de las ventanas y paginar listas. Una nube temporal puede transmitirse resumida; devolver más de un millón de posiciones a un modelo para una pregunta de tiros sería innecesario.

## Alcance que no debe prometerse

No hay penaltis, tiros libres directos, expulsiones/segunda amarilla, fuera de juego, lesiones ni prórroga anotados; tampoco formaciones distintas de 433. El esquema dispone de períodos, alineaciones y detalles para representarlos, pero esta carga no certifica esos escenarios. Las capturas 360 siguen siendo coordenadas anónimas de tiros, no imágenes. La identidad de jugadores procede del tracking y del freeze frame identificado.

El xG es una fórmula sintética documentada. xT, OBV, EPV, post-shot xG y pitch control requieren modelos que no están almacenados. No deben presentarse como métricas disponibles sólo porque haya coordenadas. Véase la explicación del proveedor sobre [modelos de valor de posesión](https://www.hudl.com/blog/possession-value-models-explained).

Para la entrega, el punto de partida recomendado es el agente de datos y sus contratos de consulta, apoyados en este catálogo y evidencia. El intérprete resolverá la intención del usuario; el constructor de dashboards recibirá datos estructurados; el analista deportivo usará los resultados y el contexto espacial para producir texto. Ninguno debe inventar una acción ausente o una puntuación cuya definición todavía no exista.
