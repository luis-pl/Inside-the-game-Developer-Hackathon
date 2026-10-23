# API de analítica deportiva

API implementada en FastAPI para las **25 operaciones de datos y nueve análisis espaciales/topológicos** del catálogo revisado. Consulta Azure SQL con la sesión Entra existente y un contexto limitado de lectura. No crea recursos de alojamiento en Azure ni modifica los partidos. El [servidor MCP](mcp.md) consume estas rutas; los agentes mantienen sus módulos reservados.

## Abrir y arrancar

Mientras el proceso esté activo en este equipo:

- Documentación interactiva: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).
- Especificación OpenAPI: [http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json).
- Catálogo de operaciones: [http://127.0.0.1:8000/api/operations](http://127.0.0.1:8000/api/operations).
- Partidos: [http://127.0.0.1:8000/api/matches](http://127.0.0.1:8000/api/matches).
- Ejemplo listo: [tiros a puerta del equipo 1 en el partido 900001](http://127.0.0.1:8000/api/matches/900001/shots?team_id=1&outcome=on_target&view=summary).

El enlace localhost funciona desde el equipo que ejecuta la API. No es un despliegue público. Al cerrar el proceso hay que arrancarlo de nuevo.

Se requiere Python 3.12 o superior, conexión a Azure y Azure CLI autenticada. Instalación normal:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
az login
```

También se conserva `requirements-windows.lock.txt` con las versiones exactas del entorno Windows verificado. Para reproducirlo con Python 3.12: instalar ese archivo y luego `pip install --no-deps -e .`. En otras plataformas se debe resolver desde pyproject.toml, porque el lock incluye las dependencias nativas de Windows.

Copia `.env.example` a `.env.local` y completa únicamente las opciones necesarias. El archivo local está excluido de Git. Si ya existe, conserva su contenido. `scripts/start-api.ps1` carga ese archivo sin ejecutar su contenido:

```powershell
.\scripts\start-api.ps1
```

También puedes definir las variables de entorno y ejecutar:

```powershell
.\.venv\Scripts\python.exe -m inside_game.cli --port 8000
```

El conector Microsoft `mssql-python` y su dependencia nativa se instalan desde Python; en este equipo no fue necesario instalar globalmente otro driver ODBC. La conexión SQL valida TLS y obtiene el token en memoria. Si Azure CLI es portable, configura AZURE_CLI_PATH; si usa otro perfil, configura AZURE_CONFIG_DIR. No introduzcas tokens en el archivo local ni en solicitudes HTTP.

## Operaciones y rutas

La ruta canónica de cada operación es **POST /api/operations/{nombre_registrado}**. Hay una ruta fija por cada nombre, con su modelo de entrada y documentación OpenAPI. Estos POST realizan consultas y cálculos de lectura; no escriben en la base.

Los GET descritos en el diseño inicial se materializaron como accesos de conveniencia para dataset, lista/ficha de partidos y tiros. El resto usa las rutas POST tipadas. El adaptador MCP ya está implementado y llama a estas rutas HTTP, reutilizando los contratos del registro y la lógica de `AnalyticsService.execute` a través de la API.

| Grupo | Operaciones implementadas |
|---|---|
| Descubrimiento | describe_dataset, find_entities, list_matches, get_match_context |
| Informes y comparación | get_team_summary, get_player_summary, get_metric_series, compare_entities, get_rankings |
| Acciones | get_events, get_shots, get_passes, get_defensive_actions, get_ball_actions, get_discipline, get_substitutions |
| Secuencias | get_possessions, get_sequences, get_set_piece_sequences |
| Seguimiento y mapas | get_tracking_frame, get_tracking_window, get_event_context, get_heatmap, get_movement_summary, get_zone_summary |
| Análisis espacial | get_team_shape, get_proximity_connectivity, get_space_coverage, get_passing_network, get_pass_corridor, get_line_breaks, get_persistent_structure, get_node_removal_robustness, get_defensive_profile |

## Primera consulta desde Swagger

Abre /docs, despliega POST /api/operations/get_shots, pulsa Try it out, sustituye el cuerpo y pulsa Execute:

```json
{
  "match_id": 900001,
  "team_id": 1,
  "outcome": "on_target",
  "scope": {"kind": "match"},
  "view": "map",
  "limit": 100
}
```

En los datos auditados, el equipo 1 tiene **seis tiros a puerta** en ese partido. La respuesta devuelve el total completo y una página de eventos, con IDs, reloj, posición y datos del tiro; también contiene método, procedencia y advertencias. Un total nunca se limita al tamaño de la página.

Otros ejemplos de cuerpos:

```json
{
  "match_id": 900001,
  "kind": "aerial_duel",
  "team_id": 1,
  "outcome": "won",
  "view": "events"
}
```

```json
{
  "match_id": 900001,
  "team_id": 1,
  "period": 1,
  "time_ms": 600000,
  "epsilon_m": 15,
  "view": "matrix"
}
```

El primer cuerpo corresponde a get_defensive_actions; el segundo a get_proximity_connectivity. Las listas, perfiles y límites completos están en OpenAPI y en /api/operations.

## Definiciones y límites

- Scope es match, period o window. Una ventana usa reloj local al período y es [start_ms,end_ms). El período es obligatorio para ventanas y snapshots. No se cruza el descanso al calcular desplazamientos.
- Tracking exige segundos muestreados: no interpola silenciosamente. Ventanas crudas: máximo 120 s; series espaciales: máximo 60 frames. El fin de un período puede pedirse como snapshot, pero no suma un segundo a los minutos.
- Los informes de equipo/jugador admiten hasta diez partidos. Los jugadores o equipos solicitados expresamente deben pertenecer a esos partidos. Los rankings consideran los partidos compatibles de cada entidad y publican sus minutos y tamaño de muestra.
- Las listas usan páginas de hasta 200 elementos y cursores firmados ligados a la consulta y revisión. No aceptan offsets o SQL del cliente.
- Los resúmenes y comparaciones incluyen informes por partido y agregados; las tasas agregadas se recalculan con los numeradores/denominadores totales. No se promedian porcentajes sin ponderación.
- get_metric_series admite perfiles de eventos. movement y ppda_demo se consultan mediante sus informes correspondientes, no como series en esta implementación; la combinación no soportada devuelve un error explícito.
- Los heatmaps de ocupación admiten participante y tiempo; los filtros de acción se aplican al modo event_count. La ocupación de equipo se expresa en jugador-segundos, no en segundos únicos de equipo.
- Los tercios usan coordenadas métricas ofensivas: [0,35), [35,70) y [70,105]. El área es x≥88,5 m y y entre 13,84 y 54,16 m; el corredor central cubre el tercio lateral central.
- Un pase progresivo completado reduce al menos 10 m la distancia al centro de la portería. La distancia total de pase se recalcula en metros, sin usar directamente la longitud 120×80 del proveedor.
- En conducciones se publica desplazamiento entre extremos y progresión; no se presenta ese desplazamiento como longitud exacta del recorrido. La distancia del jugador usa su tracking entre muestras válidas.
- Las recepciones y pérdidas posteriores conservan sus tipos. Los duelos aéreos se devuelven como disputas con ganador/perdedor; una consulta global puede incluir ambas perspectivas en el mismo registro. Los 50/50 globales se deduplican; con actor/equipo se conserva la perspectiva correspondiente.
- pressure_effectiveness une intervalos para tiempo único y distingue suma de duraciones. Su recuperación posterior usa cinco segundos y censura presiones sin ventana completa de seguimiento. Es asociación temporal, no causalidad.
- ppda_demo es una definición propia: intentos de pase regular rival con x ofensiva≤63 m divididos por quites/intercepciones/faltas propias con x ofensiva≥42 m. Es de equipo, sin filtros adicionales de zona/presión/marcador; cero en el denominador produce null.
- get_sequences ofrece cuatro patrones cerrados: pases consecutivos A-B-A, acción del mismo jugador tras regate en diez segundos y la misma posesión, recuperación→tiro en la nueva posesión hasta sesenta segundos, y presión→recuperación hasta cinco segundos. Las ventanas solicitadas limitan también los desenlaces.
- Portería agrega paradas sin duplicar el tiro Saved y su evento Goal Keeper. Los informes calculan tiros a puerta enfrentados, goles concedidos y tasa de parada con los resultados de tiros rivales; los intervalos del portero delimitan su participación.
- Los cálculos espaciales exigen posiciones para todos los participantes activos. La forma/conectividad usa jugadores de campo; la cobertura Voronoi y los corredores consideran porteros. Rips fija H0/H1, F2, dimensión 2 y corte de 40 m; los intervalos supervivientes al corte se identifican como censurados.
- El perfil defensivo usa anclas de pases/tiros rivales y devuelve forma, conectividad, rivales en la envolvente, cercanía al balón/corredores y tiros/xG concedidos. No etiqueta la fase defensiva en todos los segundos ni devuelve una probabilidad de impenetrabilidad. El corredor de pase es estático y sólo se admite para pases rasos; no hay un modelo 3D de intercepción o bloqueo de tiros.
- Cada consulta tiene timeout SQL de 15 s y presupuesto HTTP de 30 s. Una conexión fría al SQL gratuito puede superar ese presupuesto: se devuelve 503 y puede reintentarse. Una operación que supera tamaño/cobertura no trunca silenciosamente el resultado. El trabajo ya iniciado se mantiene dentro del límite de concurrencia hasta acabar.
- Los cuerpos se limitan a 64 KiB y las respuestas a 1 MiB; hay un límite por identidad de 120 solicitudes/minuto y cuatro solicitudes activas por proceso. Para varios procesos/hosts se necesitaría un limitador compartido.

## Permisos y autenticación

El arranque normal se limita a 127.0.0.1. Las peticiones desde loopback y dirigidas a localhost pueden usar la documentación sin clave. Un cliente remoto necesita bearer API key. Para enlazar a una interfaz pública, el CLI exige INSIDE_GAME_LOCAL_ACCESS=false y una clave de al menos 32 caracteres. No publiques el puerto directamente en Internet: un alojamiento público requiere HTTPS y configuración de red del entorno.

El SQL runtime exige el rol football_reader y rechaza identidades con permisos de administración/escritura comprobados. La API local baja su contexto a `inside_game_api_reader`, usuario sin login creado para esta tarea y miembro de ese rol. Se ejecuta REVERT antes de devolver la conexión al pool.

Para preparar otra base, un administrador ejecuta una vez `database/azure-sql/api-reader.sql`. El helper `bootstrap-api-reader.mjs` lo aplica y comprueba permisos. El servidor API no crea usuarios ni altera tablas al arrancar. En un alojamiento futuro se debe asignar una identidad propia con lectura; no reutilizar la cuenta personal de administrador como identidad de servicio.

No se admiten texto SQL, nombres libres de columnas/tablas, fórmulas, JSONPath o código. Las propiedades y combinaciones no soportadas se rechazan. Los errores externos no revelan consultas, tokens ni trazas. Las credenciales no se almacenan en el repo.

## Verificación

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/verify_api.py
```

Las pruebas unitarias/HTTP usan una fixture pequeña y no requieren Azure. El script de integración es de lectura y prueba las 34 operaciones con las filas de la nube; registra resultados y comprobaciones en [api-verification.json](api-verification.json). Los tests incluyen rechazo de SQL/campos extra, autenticación, límites, cursores, ventanas, sustituciones, deduplicación, PPDA y propiedades matemáticas de MST, Rips y Voronoi.

El /health confirma que el proceso responde; no afirma que Azure esté disponible. Los escenarios sin anotaciones y los modelos no implementados siguen siendo los detallados en [DATA-QUALITY.md](../database/azure-sql/DATA-QUALITY.md): no se inventan penaltis, expulsiones, xT, pitch control ni una puntuación calibrada de defensa.
