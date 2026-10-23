"""Document the delivery scope from the measured Azure dataset; no API code."""
import collections
import json
import pathlib

root=pathlib.Path(__file__).parents[2]
evidence=json.loads((root/'docs/data-capabilities-evidence.json').read_text(encoding='utf-8'))
assert evidence['status']=='passed'
assert {r['generator_version'] for r in evidence['sections']['matches']}=={'3.0.0'}
families=[]

def family(id,tool,title,sources,rows):
    operations=[]
    for line in rows.strip().splitlines():
        key,status,label,definition=line.split('|',3)
        operations.append({'id':f'{id}.{key}','status':status,'label':label,'definition':definition})
    families.append({'id':id,'proposed_interface':tool,'title':title,'source_tables':sources.split(','),'operations':operations})

family('catalog','describe_dataset','Descubrimiento y cobertura','matches,events,tracking_runs',r'''
capabilities|observed|Capacidades del conjunto|Campos, tipos de evento, dominios observados y operaciones con estado de disponibilidad.
quality|observed|Procedencia y calidad|Versión sintética, muestreo, cobertura por jugador/período, NULL, límites y convenciones de coordenadas.
schema|observed|Esquema y relaciones|Metadatos de las 30 tablas y 250 columnas; describir las vistas analytics como superficie de lectura.
domains|observed|Valores disponibles|Enumeraciones realmente presentes para resultados, banderas, períodos, formatos y tipos de pase.
''')
family('entities','find_entities','Búsqueda de entidades','competitions,seasons,competition_seasons,matches,teams,players,managers,stadiums,referees',r'''
competitions|observed|Competición y temporada|Identificadores y nombres; una competición y una temporada en esta carga.
matches|observed|Buscar partidos|Filtrar por equipo, rival, fecha, local/visitante y resultado; no asumir calendario completo.
teams|observed|Buscar equipos|Cuatro equipos sintéticos, nombres y encuentros disponibles.
players|observed|Buscar jugadores|56 inscritos; distinguir titulares y suplentes que ingresan, por partido e intervalo de actividad.
staff_venues|observed|Personal y sede|Entrenadores, árbitros y estadios; son atributos sintéticos de contexto.
''')
family('context','get_match_context','Contexto del partido','matches,match_teams,match_lineups,lineup_positions,lineup_cards,event_tactics,tactical_lineups,match_team_managers',r'''
summary|observed|Ficha del encuentro|Fecha, hora sin zona UTC inferida, equipos, marcador, sede y versión del conjunto.
lineups|observed|Alineaciones y posiciones|Titulares, suplentes, dorsal y posición declarada; on_pitch_slot no equivale al dorsal ni al ID de posición.
tactics|observed|Formación declarada|Starting XI y Tactical Shift con formación 433; los cambios actualizan participantes, no representan una variación de formación.
cards|observed|Tarjetas|Amarillas registradas; vincular faltas y jugadores por partido, período y reloj exacto.
minutes|computable|Minutos cubiertos|Intersección entre presencia activa, períodos y ventana solicitada; excluir el extremo final de cada período y los intervalos de jugadores sustituidos.
substitutions|observed|Sustituciones|Actor saliente y replacement entrante en details, con alineaciones e identidades de tracking actualizadas desde el segundo siguiente.
score_state|computable|Marcador en un instante|Acumular goles por período, reloj e índice; conservar el marcador anterior al inicio de la ventana.
results|computable|Resultados comparados|Victorias, empates y derrotas sobre los partidos disponibles; tabla parcial, no clasificación oficial.
''')
family('events','query_events','Exploración de acciones','events,event_relations',r'''
filter|observed|Filtrar acciones|Por partido, equipo, jugador, tipo, período, reloj, posesión, resultado, banderas y zona.
timeline|observed|Cronología|Ordenar por período, period_time_ms y event_index; no usar sólo el minuto global.
relations|observed|Relaciones entre eventos|Devolver extremos tipados; el enlace por sí solo no prueba causalidad ni equivale a una asistencia.
counts|computable|Frecuencias y series|Conteos por actor, zona, minuto, ventana y estado del marcador, con denominador explícito.
chains|computable|Secuencias registradas|Eventos anteriores y posteriores, motivos de tipos y cadenas dentro de una posesión/período.
''')
family('shots','query_shots','Finalización y creación','events,event_shots,event_passes,event_relations',r'''
list_map|observed|Lista y mapa de tiros|Tiros con origen, final 3D, jugador, instante, resultado y xG sintético; cantidades verificadas en el perfil adjunto.
on_target|computable|Tiros a puerta|IDs 97, 100 y 116; excluir tanda por defecto. En esta carga: goles + Saved; no contar Blocked ni Off T.
outcomes|computable|Resultados del tiro|Goles, paradas, bloqueos y fuera; 99/115/116 no aparecen en esta carga.
xg|computable|xG agregado y acumulado|Sumar statsbomb_xg sin recalcularlo; devolver xg_model=toy-distance-angle-v2 e is_synthetic=true.
quality|computable|Calidad y eficacia|xG/tiro, goles/tiro, goles menos xG y proporción a puerta; dividir por cero produce NULL con motivo.
geometry|computable|Distancia y ángulo de tiro|Convertir primero a metros; centro y postes según campo/portería de la configuración del run.
assists|observed|Pases clave y asistencias|key_pass_id relaciona el pase completado con el tiro del receptor; goal_assist exige resultado Goal.
chains_xg|computable|xG de cadenas registradas|Asignar xG de posesiones a participantes ofensivos observados; no afirmar cobertura de todos los toques ni equivalencia automática con un producto xGChain.
conceded|computable|Tiros y xG concedidos|Perspectiva del rival con filtros simétricos; son indicadores descriptivos del escenario sintético.
keeper|computable|Actividad de portería|Shot Saved y tiros Saved representan las mismas paradas: enlazar sin contarlas dos veces; tasa sobre tiros a puerta definidos.
headers|observed|Cabezazos y superficie de remate|Comparar Head, Left Foot y Right Foot, con altura del balón, first_time, xG y resultado.
special_types|unobserved|Penaltis y tiros libres directos|No hay tiros Penalty ni Free Kick. Los pases desde faltas no sustituyen esos escenarios.
postshot|needs_model|Post-shot xG o xGOT|No existe un modelo post-tiro ni valores almacenados; la geometría por sí sola no los proporciona.
''')
family('passes','query_passes','Circulación y progresión','events,event_passes',r'''
list_map|observed|Trayectorias de pase|Extremos, longitud, ángulo, duración, altura y receptor cuando se completó.
completion|computable|Pases y acierto|En esta fuente outcome NULL significa completado; una pérdida posterior por regate fallido o mal control no vuelve incompleto el pase recibido.
receptions|observed|Recepciones anotadas|Eventos Ball Receipt* enlazados con el pase completo, actor e instante de llegada; no representan todos los toques del partido.
progression|computable|Progresión y distancia|Metros ganados hacia portería y reducción de distancia al gol; umbral de pase progresivo parametrizado y publicado.
entries|computable|Entradas a zonas|Detectar cruces de frontera por origen/final hacia tercio final, área o zona configurada en metros.
directions|computable|Dirección del pase|Adelante, atrás y lateral según componente longitudinal y tolerancia declarada.
pressure_split|computable|Rendimiento bajo presión|Comparar acierto/progresión con y sin under_pressure, sin atribuir causalidad.
restarts|computable|Reanudaciones|Tiro libre indirecto/pase, saque de meta, saque de centro, córner y saque de banda. No confundir Free Kick de pase con tiro libre directo a portería.
combinations|computable|Sociedades y secuencias|Pares emisor-receptor, A-B-A y cadenas temporales de pases completos de la misma posesión.
territory|computable|Cuota territorial de pases|Participación de pases/recepciones en zonas ofensivas con denominador explícito; no llamarlo posesión temporal.
annotations|partial|Centros y etiquetas especiales|cross, cut_back y switch tienen una definición geométrica sintética explícita; through_ball y technique siguen sin anotación. Distinguir false de NULL y etiqueta de simulación de observación real.
pattern_candidates|proxy|Cambios de orientación o pases filtrados geométricos|Puede detectarse un patrón por extremos/distancias/posiciones, etiquetado como inferido y con umbrales; no reemplaza la etiqueta original.
''')
family('defense','query_defensive_actions','Defensa y presión','events,lineup_cards,event_shots,event_tracking_links,tracking_player_positions,tracking_ball_positions',r'''
pressures|observed|Acciones de presión|Acciones Pressure con counterpress cuando corresponde; under_pressure es presión recibida y counterpress es una bandera aparte.
duels|observed|Duelos y 50/50|Separar Tackle de Aerial Lost y 50/50; cada disputa puede tener perspectivas de ambos participantes, no sumar filas como disputas distintas.
recoveries|observed|Recuperaciones|Ball Recovery con instante, actor, zona y contexto de secuencia.
discipline|computable|Faltas y disciplina|Foul Committed y Foul Won son perspectivas de la misma falta: no sumarlas como faltas distintas.
pressure_time|computable|Duración de presión|Entregar suma de duraciones y, por separado, unión de intervalos por equipo/período para tiempo único.
pressure_outcomes|proxy|Resultado posterior a presión|Recuperación/pase fallado/tiro dentro de ventana configurable y mismo período; asociación temporal, no prueba de éxito causal.
transitions|computable|Cambios de posesión registrados|Identificar cambio de equipo por posesión y event_index; excluir cabeceras y reinicios al definir pérdidas en juego.
recovery_delay|proxy|Tiempo hasta recuperar|Medir entre cambios registrados y recuperación con cobertura; no asumir que todos los contactos tienen evento.
ppda|proxy|PPDA definido para la demo|Pases rivales en zona declarada / acciones defensivas elegidas allí; documentar tipos incluidos y no presentarlo como PPDA de un proveedor sin reproducir su definición.
blocking|observed|Bloqueos|Eventos Block con actor y relación con Shot Blocked; no contar ambas filas como dos tiros bloqueados.
interceptions|observed|Intercepciones|Interception, resultado Success In Play, posición de contacto y cambio posterior de equipo con balón.
tackles|observed|Quites|Duel/Tackle es un intento del defensor: Won al desposeer al portador, Lost In Play si ese defensor es superado. Dispossessed describe al portador; no es un intento de quite perdido por él.
clearances|observed|Despejes|Clearance, cuerpo, extremo de trayectoria y aerial_won; incluir despejes al lateral seguidos de saque de banda rival.
aerial|observed|Duelos aéreos ganados y perdidos|El perdedor tiene Duel/Aerial Lost; el ganador un Clearance con aerial_won=true, enlazado a ese duelo. No existe un tipo inventado Aerial Won.
''')
family('ball_skills','query_ball_actions','Regates, conducciones y pérdidas','events,event_relations,event_tracking_links,tracking_player_positions,tracking_ball_positions',r'''
dribbles|observed|Regates por resultado|Dribble con outcome Complete/Incomplete; posiciones, instante, adversario y relación con Dribbled Past o Dispossessed.
dribble_rate|computable|Éxito de regate|Completos / intentos, por jugador, zona, presión o intervalo; describir el denominador y mantener NULL cuando no hay intentos.
carries|observed|Conducciones|Carry, duración, end_location y tracking del mismo jugador controlando el balón; separar conducción de pase y de regate anotado.
carry_progression|computable|Progresión con balón|Desplazamiento hacia el gol y distancia recorrida durante las conducciones, entradas al área/tercio final y conexiones con la acción siguiente.
miscontrols|observed|Malos controles y desposesiones|Miscontrol y Dispossessed tienen significados distintos; no convertir automáticamente todo pase fallado en pérdida individual por regate.
lost_zones|computable|Mapa de pérdidas|Unificar secuencias de mal control, regate fallido o pase incompleto por reglas publicadas para evitar contabilizar dos veces la misma pérdida.
after_dribble|computable|Acción tras superar un rival|Encontrar pase, tiro o pérdida posterior en la misma posesión, con ventana y continuidad explícitas.
''')
family('possessions','get_possessions','Posesiones y ataques','events,event_passes,event_shots,tracking_frames',r'''
sequences|observed|Posesiones registradas|Agrupar por match_id/possession; el entero local no identifica una posesión global.
structure|computable|Características de ataque|Equipo, jugadores observados, pases, zonas, final, tiro y xG asociado de cada secuencia.
duration|proxy|Duración estimada de posesión|El primer/último evento no delimita todos los intervalos; definir propagación, límite de huecos y exclusión de balón parado.
share|proxy|Porcentaje temporal de posesión|No hay propietario por frame. Inferir con método explícito y reportar segundos sin asignar; conteo de eventos o posesiones no es posesión temporal.
directness|computable|Verticalidad y recorrido|Progresión longitudinal / recorrido observado y eventos antes del tiro, con fórmula y acciones incluidas publicadas.
attack_outcomes|computable|Final de ataque y transición|Posesiones con tiro, gol, pase fallado o siguiente equipo; no considerar automáticamente todo reinicio una recuperación defensiva.
''')
family('tracking','get_tracking','Posiciones y movimiento','tracking_runs,tracking_periods,tracking_frames,tracking_player_positions,tracking_ball_positions',r'''
frame|observed|Posición en un segundo|Seleccionar explícitamente run_id y período: 22 jugadores y balón por frame, coordenadas fijas en metros.
window|observed|Ventanas y reproducción|Intervalos, jugadores/equipos, stride, balón y ball_in_play; reproducción del registro, sin vídeo ni alimentación en directo.
trajectories|observed|Trayectorias|Recorridos por jugador y balón separados por período y generación, con presencia y estado de posición.
distance|computable|Distancia recorrida|Suma de distancias entre muestras consecutivas válidas; separada de desplazamiento neto y sin saltar huecos/períodos.
kinematics|proxy|Velocidad y aceleración muestreadas|Diferencias finitas con dt real, método y suavizado declarados; no velocidad/acceleración instantánea profesional.
speed_zones|computable|Tiempo por umbral de velocidad|Intervalos de velocidad muestreada con umbrales publicados; resultados y cobertura dependen del muestreo a 1 Hz.
ball|computable|Movimiento del balón|Recorrido 2D/3D, altura, velocidad muestreada y tiempo vivo/parado; evitar equiparar 54.020 muestras con 54.020 segundos.
subsecond|proxy|Instantes intermedios|Interpolación explícita con bracket válido del mismo período/run; nunca declarar que se observó un instante sin muestra.
presence|observed|Presencia y sustituciones|14 inscritos y 11 activos por equipo en cada segundo. Los 14 participan en intervalos distintos; fuera de su intervalo no hay coordenadas observadas en cancha.
''')
family('context_event','get_event_context','Contexto espacial de una acción','events,event_relations,event_shots,event_passes,frames_360,frame_360_players,shot_freeze_players,event_tracking_links,tracking_frames,tracking_player_positions',r'''
related|observed|Acción y eventos asociados|Evento seleccionado con pase clave, tiro, parada o relación, respetando IDs y cardinalidades.
positions|observed|Jugadores y balón alrededor del evento|Tracking identificado disponible para todos los eventos; ventana anterior/posterior separada por período.
freeze|observed|Freeze frame de tiro|Cada tiro tiene captura con jugadores identificados, compañeros/rivales y posiciones del tiro, incluidas las sustituciones.
360|observed|Captura 360|Capturas de tiros con 22 participantes anónimos; no existe player_id en frame_360_players.
neighbors|computable|Jugadores cercanos|Radio, rival más próximo, conteo alrededor de actor/ball y distancias; calcular en metros sobre un único sistema.
identity|partial|Identidad en 360|Usar la identidad del tracking o del freeze frame; no adjudicar automáticamente IDs a las filas anónimas por índice o coincidencia aproximada.
''')
family('spatial','get_spatial_aggregates','Mapas, ocupación y forma','tracking_player_positions,tracking_frames,tracking_periods,events,event_passes,lineup_positions',r'''
event_heatmap|computable|Mapa de acciones|Conteos/densidades de acciones; no equivale a tiempo ocupado.
tracking_heatmap|computable|Mapa de ocupación temporal|Ponderar por dt al siguiente frame, sin último punto extra ni atravesar huecos; especificar si sólo balón en juego.
zone_time|computable|Tiempo y entradas en zonas|Intersección con polígonos o cuadrícula, dt y cruces; interpolación de fronteras sólo como estimación declarada.
centroid|computable|Centroide del equipo|Media x/y de participantes seleccionados; excluir portero por defecto y fijar orientación y fase.
shape|computable|Ancho y longitud|Extensión lateral y longitudinal, radio de giro y distancias medias al centroide en metros.
hull|computable|Área del bloque|Envolvente convexa y área m² de puntos elegidos; no equivale a territorio controlado ni huecos internos.
line_height|computable|Altura de línea y separación|Agrupar por roles declarados o por agrupación geométrica explícita; publicar método. El dorsal/slot no define una línea táctica.
balance|computable|Superioridades locales|Contar atacantes/defensores dentro de radio o zona y jugadores entre balón y portería.
voronoi|proxy|Territorio por proximidad|Celdas recortadas al campo o zona, puntos duplicados/degenerados controlados; territorio geométrico no es pitch control probabilístico.
lanes|proxy|Corredores de pase y tiro|Distancia de rivales a segmentos/corredores y márgenes; análisis geométrico estático, no probabilidad de intercepción.
line_breaks|proxy|Rupturas de línea|Cruces de líneas definidas e individuos superados según frame y dirección elegidos; no una anotación de origen.
space_model|needs_model|Pitch control y tiempo de llegada|Requiere modelo de movimiento/reacción y calibración; el tracking a 1 Hz y Voronoi no lo convierten en un dato medido.
''')
family('metrics','aggregate_metrics','Agregaciones y series','events,event_passes,event_shots,tracking_frames,tracking_player_positions',r'''
group|computable|Agrupación de métricas|Por partido, equipo, jugador, rol declarado, período, zona, ventana, estado del marcador o presión.
series|computable|Series y acumulados|Bins temporales y ventanas móviles con límites por período y denominadores/cobertura.
rates|computable|Tasas y razones|Por intento, posesión registrada, minuto cubierto o 90 minutos; los ceros de denominador no generan infinitos.
ranking|computable|Rankings y contribuciones|Ordenar métricas verificables sobre el subconjunto disponible con número de partidos/minutos y procedencia sintética.
associations|proxy|Asociaciones descriptivas|Relacionar forma/espacio/presión con resultado posterior; diez partidos sintéticos no validan causalidad ni generalización.
models|needs_model|xT, OBV, EPV y calidad defensiva compuesta|No existen pesos, superficies o modelos calibrados. Elegir una definición explicable antes de exponer una puntuación.
''')
family('compare','compare_entities','Comparaciones coherentes','matches,events,event_passes,event_shots,tracking_player_positions',r'''
players|computable|Comparar jugadores|Mismos filtros, métricas, umbrales, minutos cubiertos y condición de titular/suplente.
teams|computable|Comparar equipos|Con/sin balón según clasificación explícita, local/visitante, rival y partidos presentes.
periods|computable|Comparar tiempos e intervalos|Separar primer/segundo tiempo y ventanas con distintas duraciones; no mezclar sus relojes locales.
states|computable|Comparar escenarios observados|Ganando/empatando/perdiendo, bajo presión/libre y antes/después de sustituciones; describir asociación y tamaño de muestra.
''')
family('bundles','prepare_analysis_bundle','Entradas para topología y analista','events,event_passes,event_tracking_links,tracking_frames,tracking_player_positions,tracking_ball_positions,lineup_positions',r'''
passing_network|computable|Red de pases observados|Nodos activos, aristas dirigidas y ponderadas por pases completos, cronología y posiciones de nodos con método declarado.
graph_metrics|computable|Conectividad de red de pases|Grados, strengths, densidad, componentes, centralidades y vulnerabilidad matemática; declarar dirigido/ponderado y uso de pesos como fuerza o coste.
point_cloud|observed|Nubes de puntos sincronizadas|IDs, equipo, rol, x/y en metros, balón, período/run/reloj y máscara válida; separar equipo defensor/atacante por evidencia o inferencia de fase.
distance_matrix|computable|Matrices de distancias|Entre compañeros, rivales y balón; simetría y diagonal para matrices de una misma nube.
proximity_graph|computable|Red de proximidad|Umbral métrico o k vecinos declarado, portero opcional, componentes, grados y radio de conexión; no confundir con pases ejecutados.
triangulation|computable|Triangulación espacial|Delaunay o triangulación declarada, celdas y adyacencias con política de degeneración; datos de entrada disponibles.
defensive_episode|computable|Episodio de defensa|Secuencia de frames, acciones, marcador y tiro/pase desenlace para aplicar funciones aún por definir.
topological_features|needs_definition|Persistencia y topología espacial|La nube admite filtraciones Rips/Čech/alfa, pero hay que fijar complejo, escala y dimensión. Un ciclo de grafo no es automáticamente un hueco explotable.
robustness|proxy|Robustez matemática ante retirar nodos|Recalcular conectividad al retirar un jugador del grafo; es una perturbación del modelo, no predecir una expulsión o sustitución real.
impenetrability|needs_definition|Impenetrabilidad defensiva|Proponer un perfil explicable de compactación, separaciones, corredores y resultados concedidos; no existe una verdad almacenada ni un score universal.
''')

statuses={'observed':'Observado/consultable en la carga',
 'computable':'Derivable con cálculo determinista y definición publicada',
 'proxy':'Estimación o indicador con supuestos explícitos',
 'partial':'Cobertura parcial, uniforme o desconocida según campo',
 'unobserved':'Sin eventos/variación registrados en la carga actual',
 'needs_model':'Requiere un modelo externo o calibración no disponible',
 'needs_definition':'Entradas disponibles; falta elegir la función matemática'}
operations=[o for f in families for o in f['operations']]
assert len({o['id'] for o in operations})==len(operations)
assert all(o['status'] in statuses for o in operations)
schema={r['table_name'] for r in evidence['sections']['tableCounts']}
assert all(t in schema for f in families for t in f['source_tables'])
catalog={'purpose':'Final hackathon capability scope proposal, not deployed agent/API/MCP functionality',
 'evidence_observed_at':evidence['observedAt'],'dataset_version':'3.0.0','family_count':len(families),'operation_count':len(operations),
 'status_definitions':statuses,'status_counts':dict(collections.Counter(o['status'] for o in operations)),
 'common_dimensions':['match_ids','team_ids','player_ids','run_id','period','start_ms','end_ms','event_types','outcomes','flags','zone','group_by','time_bin','score_state'],
 'families':families}
(root/'docs/data-operations-catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
lines=['# Catálogo de operaciones de datos para la entrega de la hackathon',
 'Propuesta de alcance basada en consultas de lectura a Azure. No representa funciones de agentes/API/MCP ya implementadas.',
 f"{len(families)} familias de interfaz y {len(operations)} capacidades analizadas. Cada familia combina filtros, agrupaciones y ventanas; no hace falta una tool por cada pregunta.",
 '## Estados']
lines += [f'- **{k}**: {v}.' for k,v in statuses.items()]
for f in families:
    lines += [f"## {f['title']}: `{f['proposed_interface']}`",'Tablas: '+', '.join('`'+t+'`' for t in f['source_tables'])+'.',
              '| ID | Estado | Operación y definición |','|---|---|---|']
    lines += [f"| `{o['id']}` | {o['status']} | **{o['label']}**. {o['definition']} |" for o in f['operations']]
(root/'docs/data-operations-catalog.md').write_text('\n\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'families':len(families),'operations':len(operations),'statuses':catalog['status_counts']}))
