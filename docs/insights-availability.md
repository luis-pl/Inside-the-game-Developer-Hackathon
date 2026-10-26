# Disponibilidad de las treinta recetas por fuente

Primer paso del agente de insights: saber qué puede mostrar con datos reales antes
de construir el agente. Sin LLM. `scripts/insights_availability.py` pide a la API
de Azure la evidencia de cada receta para un partido de cada fuente y la compila
con el mismo `compile_report` que usa el MCP de insights. Las consultas las decide
el resolvedor del agente (`src/inside_game/agents/insights_agent/resolver.py`), de
modo que la matriz verifica también al resolvedor.

```powershell
.\.venv\Scripts\python.exe scripts/insights_availability.py --write-profiles
```

`--write-profiles` regenera `agents/insights_agent/source_profiles.json`: las
recetas imposibles o engañosas (sólo ceros) por fuente que el agente descarta.

Resultado: [insights-availability.json](insights-availability.json) y una página
HTML por partido en `.temp/insights/availability/`. Unas 25 consultas por partido;
el script respeta el límite de 120 consultas/min y reintenta el 503 de arranque.

## Partidos y decisiones del anfitrión

| Partido | Fuente | Instante analizado | Roles declarados |
|---|---|---|---|
| 900001 | **Sintético** 3.0.0 | P1 10:00 | Posiciones anotadas por la fuente (4 DEF, 3 MED, POR) |
| 900011 | Metrica real anonimizado | P1 10:00 | Sólo portero; la fuente no anota otras posiciones |
| 900101 | SkillCorner real seudonimizado | P1 15:00 | Posiciones anotadas por la fuente |

- Equipo analizado: local. Orientación: `periods.home_attacks_positive_x` del contexto.
- Roles: `position_intervals` activos en el instante; nunca por dorsal.
  Recepciones entre líneas usa las líneas del **rival**.
- SkillCorner es tracking de broadcast: en P1 10:00 faltan jugadores fuera de
  cámara (`INSUFFICIENT_COVERAGE`); se elige el primer instante con cobertura completa.
- Pase ↔ tracking: ventana de 60 s anclada en pases completados del local desde el
  instante (≥3 pases), con límites redondeados al segundo y tolerancia explícita
  de 500 ms para el tracking a 1 s de las fuentes reales.

## Matriz

`ready*` = el renderer dice "Disponible" pero sólo hay contadores a cero (ver hallazgo 1).

| Receta | 900001 sint. | 900011 Metrica | 900101 SkillCorner |
|---|---|---|---|
| shot_map | ready | ready | ready |
| xg_story | ready (xG ilustrativo) | unavailable: sin xG | unavailable: sin xG |
| match_timeline | ready | ready | ready |
| pass_map | ready | ready | ready |
| passing_network | ready | ready | ready |
| sequence_explorer | ready | ready | ready |
| defensive_actions | ready | ready | **ready\*** |
| pressure_recovery | ready | ready | **ready\*** |
| ball_progression | ready | **ready\*** | **ready\*** |
| occupation_heatmap | ready | ready | ready |
| movement_profile | ready | ready | ready |
| play_replay | ready | ready | ready |
| zone_presence | ready (sólo métricas) | ready (sólo métricas) | ready (sólo métricas) |
| team_shape | ready | ready | ready |
| proximity_network | ready | ready | ready |
| space_partition | ready | ready | ready |
| persistent_structure | ready | ready | ready |
| node_robustness | ready | ready | ready |
| entity_comparison | ready | ready | ready |
| defensive_geometry | ready | unavailable: API 422 sin roles mapeados | unavailable: API 422 |
| defensive_line_height | ready | unavailable: sin defensores anotados | ready |
| goalkeeper_connection | ready | unavailable: sin defensores anotados | ready |
| final_third_channels | ready | ready | ready |
| between_lines_receptions | ready | unavailable: sin roles | partial: pases sin snapshot compatible |
| ball_recovery_time | ready | ready | ready |
| pressure_turnovers | ready | unavailable: sin presión anotada | unavailable: sin presión anotada |
| structural_pass | ready | ready | ready |
| hodge_flow | ready | ready | ready |
| topological_change | partial: pares no comparables | ready | ready |
| clearance_connectivity | ready | ready | ready |

Totales: sintético 29 ready, 1 partial; Metrica 24 ready (1 con ceros),
6 unavailable; SkillCorner 26 ready (3 con ceros), 1 partial, 3 unavailable.

## Hallazgos para el agente

1. **"Disponible" con ceros cuando la fuente no anota la acción.** SkillCorner no
   anota quites, duelos, regates ni conducciones; Metrica no anota regates ni
   conducciones. El bloque sale `ready` y muestra "tackles won 0". El catálogo
   dice "vacío sin cobertura no significa cero", pero el adaptador marca `ready`
   porque el diccionario de métricas no está vacío. Debería ser
   `empty_with_coverage` o `unavailable`. Corregir en `insights/adapters.py`
   (coordinar con el autor) o filtrar en el agente hasta entonces.
2. **El agente debe aportar parámetros que el usuario no dirá.** Equipo
   (`ball_recovery_time`, `pressure_turnovers`), orientación y roles de la fuente
   (`defensive_line_height`, `goalkeeper_connection`, `between_lines_receptions`,
   `structural_pass`) e instante con cobertura completa en SkillCorner. Sin ellos,
   10 recetas del sintético salían `unavailable` en la primera pasada.
3. **Límites reales de fuente** que el agente no debe ofrecer: xG fuera del
   sintético, rupturas de línea (`get_line_breaks`) fuera del sintético, presión
   en Metrica/SkillCorner y roles de campo en Metrica.
4. **Las ventanas pase ↔ tracking deben anclarse en pases.** Con la ventana fija
   P1 9:50–10:10, `between_lines_receptions` y `structural_pass` salían
   `unavailable` en el sintético: el local no da ningún pase en ese tramo. El
   mensaje del adaptador ("Faltan pases, participantes/roles o snapshots…") no
   distingue ese caso; el agente debe comprobar que el ámbito contiene pases.
   Además, la API rechaza (422) ventanas de tracking cuyos límites no caen en
   instantes muestreados: los pases de Metrica tienen milisegundos sueltos.
5. Ritmo de la API: 120 consultas/min por clave. Un informe completo de un
   partido consume ~25 consultas más páginas; el agente debe pedir sólo lo que
   necesitan las recetas elegidas.

Una ejecución acotada a tres partidos; no equivale a QA de todo el corpus. Los
perfiles se comprobaron después en los 20 partidos: [insights-validation.md](insights-validation.md).

## Plantillas con el perfil aplicado

Así las usará el agente: el resolvedor expande la plantilla, descarta con motivo
lo que la fuente no puede mostrar y calcula los parámetros. Equipo protagonista:
local; jugador de la ficha: el primer medio anotado por la fuente.

| Plantilla | 900001 sint. | 900011 Metrica | 900101 SkillCorner |
|---|---|---|---|
| match_overview | 10 ready | 9 ready · descarta xg_story | 8 ready · descarta xg_story, defensive_actions |
| player_dossier | 7 ready | 6 ready · descarta ball_progression | 5 ready · descarta ball_progression, defensive_actions |
| entity_comparison | 7 ready | 7 ready | 7 ready |
| tactical_episode | 8 ready | 6 ready · descarta defensive_line_height, between_lines_receptions | 7 ready, 1 partial |

Ningún bloque mostrado sale `unavailable`; el único `partial` declara su
denominador. La matriz generada por el resolvedor coincide celda a celda con la
del plan manual anterior.
