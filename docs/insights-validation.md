# Validación de la matriz en los 20 partidos

25 de octubre. La matriz de [insights-availability.md](insights-availability.md) se
midió con un partido por fuente (900001, 900011, 900101) y sus perfiles se aplican
a toda la fuente. Esta pasada repite la matriz y las cuatro plantillas en **los 20
partidos de la API** (10 sintéticos, 2 de Metrica, 8 de SkillCorner) para comprobar
esa generalización. Sin modelos; sólo lectura sobre la API.

```powershell
.\.venv\Scripts\python.exe scripts/insights_availability.py --match-id 900001 ... --output-dir .temp/insights/availability-all
```

Sin `--write-profiles`: los perfiles no se tocaron. Tardó menos de media hora (la
matriz, unos 8 minutos; el resto, las plantillas).

## Resultado

**Los perfiles se sostienen.** Ninguna receta pasa de disponible a no disponible
entre partidos de una misma fuente; las diferencias son sólo `partial`.

| Fuente | Partidos | Recetas con estado distinto entre partidos |
|---|---|---|
| Sintético | 10 | 1 de 30: `topological_change` `partial` en 8, `ready` en 900005 y 900006 |
| Metrica | 2 | 0 de 30 |
| SkillCorner | 8 | 2 de 30: `between_lines_receptions` `partial` en 900101, 900105 y 900108; `topological_change` `partial` en 900105 |

- Las recetas del perfil `unavailable` lo son en **todos** los partidos de su
  fuente; las del perfil `zero_only` (SkillCorner: `ball_progression`,
  `defensive_actions`, `pressure_recovery`; Metrica: `ball_progression`) devuelven
  sólo ceros en todos ellos.
- Único error de API: `get_line_breaks: SOURCE_FIELD_UNAVAILABLE`, en todos los
  partidos de Metrica y SkillCorner (límite de fuente ya conocido).
- Plantillas con el perfil aplicado (80 combinaciones): ningún bloque mostrado
  salió `unavailable`, `error` ni `incompatible`, y los descartes son idénticos en
  todos los partidos de una fuente:

| Plantilla | Sintético | Metrica | SkillCorner |
|---|---|---|---|
| match_overview | 10 bloques | 9 · descarta xg_story | 8 · descarta xg_story, defensive_actions |
| player_dossier | 7 | 6 · descarta ball_progression | 5 · descarta ball_progression, defensive_actions |
| entity_comparison | 7 | 7 | 7 |
| tactical_episode | 8 | 6 · descarta between_lines_receptions, defensive_line_height | 8 |

## Límites

- No hay prueba de regresión automática: si cambian las recetas, el resolvedor o
  la API, hay que repetir esta medición a mano.

- 20 partidos no son QA de todo el corpus. Para fuentes con pocos partidos
  (Metrica: 2) la coherencia entre partidos dice poco.
- No se revisó cada advertencia de los bloques `partial`, sólo su estado.
- No valida lo que se ve en los gráficos ni el planificador con más preguntas.
- Casos de borde con datos reales (portero, período 2, equipo visitante, instante
  sin cobertura completa) sin ejecutar.
