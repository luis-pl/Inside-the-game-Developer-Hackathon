# Agente analista deportivo

`SportsAnalyst` recibe la intención del intérprete, pide evidencia original a
Data y solicita gráficos al agente de Insights. Examina las métricas y estados
que el renderer incluye en el HTML, y entrega **texto** en español. El texto se
acompaña de referencias, hechos, alcance y trazas para poder auditarlo.

El intérprete conversacional y la interfaz con conversaciones a la izquierda,
documento central y chat a la derecha siguen siendo consumidores de este
contrato. Esta tarea implementa el analista y su integración, no ese nuevo shell.

## Estructura de análisis y referencias

El prompt editable es [`prompts/sports_analyst.md`](../prompts/sports_analyst.md).
Adapta el texto a la pregunta y a lo disponible: contexto, producción ofensiva,
circulación, estructura espacial, interpretación, limitaciones y comprobaciones
siguientes. Cada afirmación se identifica como observación, interpretación
prudente o recomendación. El orden y los apartados no fuerzan métricas ausentes.

La estructura se inspira en la relación entre acciones, fases y contexto de
[FIFA Football Language](https://www.fifatrainingcentre.com/en/game/performance-analysis/football-language-analysis/the-fifa-football-language.php).
Las redes se interpretan como relaciones dependientes del tiempo y el contexto,
siguiendo el enfoque de [Buldú et al., 2018](https://arxiv.org/abs/1807.00534).
No se afirma que las métricas locales reproduzcan algoritmos propietarios FIFA.
[Hudl StatsBomb](https://www.hudl.com/blog/expected-goals-xg-explained) explica la
dependencia del xG respecto a su modelo; el de nuestra demo es ilustrativo y no
calibrado. Las fuentes reales importadas carecen de xG.

El anfitrión crea un catálogo de `Fact` desde escalares originales de la API y
desde las métricas de los bloques generados. Conserva ruta, operación, evidencia,
procedencia y alcance. El modelo referencia `fact_ids` y escribe placeholders
`{{f-xxxxxxxxxxxx}}`; el ejecutor inserta los valores. Se rechazan referencias
inexistentes y dígitos literales en las afirmaciones. Los datos originales
permanecen fuera del texto generado y se entregan a Insights sin reescritura.

Esta validación asegura el origen de los valores referenciados, **no demuestra
automáticamente que toda interpretación lingüística sea correcta**. El modelo
todavía puede interpretar mal una cifra o formular una hipótesis débil. El prompt,
la separación de tipos de afirmación, las referencias y la revisión humana
permiten detectarlo. Un `DataResult` aportado por el cliente se considera evidencia
del anfitrión autorizado; no se autentica por sí solo contra SQL.

## Herramientas del analista

| Herramienta | Responsabilidad |
|---|---|
| `request_data` | Delegación HTTP a Data; éste usa las consultas MCP predeterminadas, incluidas las topológicas. |
| `request_insights` | Delegación HTTP a Insights con evidencia existente; lee los resultados numéricos del HTML y valida su procedencia. |
| `finish_analysis` | Devuelve texto por secciones con citas o pide aclaración; no crea HTML. |

Las funciones topológicas ya están en el MCP deportivo: `get_team_shape`,
`get_proximity_connectivity`, `get_space_coverage`, `get_persistent_structure`,
`get_node_removal_robustness`, etc. No se crea otro servidor duplicando sus
cálculos. El agente Data conserva la frontera de consultas permitidas.

Voronoi es cercanía geométrica; componentes dependen de `epsilon_m`; H1 no prueba
un hueco explotable; retirar nodos no predice el efecto real de una sustitución.
Un frame no demuestra un patrón de partido. Los avisos de fuente y datos
ausentes se mantienen, y una recuperación parcial produce un análisis parcial.

La revisión de gráficos usa sus datos semánticos, no un modelo de visión ni
observación de vídeo. El texto nunca debe afirmar que vio acciones en imágenes.

## HTTP para el intérprete y otros agentes

El transporte es el HTTP/JSON propio del proyecto bajo `/a2a/v1`, no una
declaración de compatibilidad con el SDK A2A. Comparte las credenciales Bearer
individuales, límites, protección de origen, aislamiento y TTL del servicio.

| Ruta | Comportamiento |
|---|---|
| `POST /a2a/v1/analysis` | Intención y evidencia opcional → `AnalysisResult` con texto y referencias. |
| `POST /a2a/v1/analysis-reports` | Analiza y añade ese texto a la página de Insights. Devuelve análisis y referencia de la página final. |
| `POST /a2a/v1/reports/{id}/analysis` | Añade/cambia una nota del analista como nueva revisión, conservando exactamente los bloques. No invoca LLM ni SQL. |

Ejemplo:

```json
{
  "request_text": "Analiza la forma y conectividad del equipo 1 en el partido 900001, P1 a 600000 ms. Acompaña el texto con team_shape y proximity_network y aclara sus límites.",
  "context": {"match_ids": [900001], "team_ids": [1]}
}
```

`data_result` permite reutilizar un resultado de Data. `review_visuals=true` es
el valor por defecto. En solicitudes únicamente textuales puede desactivarse;
entonces el consumidor no debe interpretar la ausencia de página como un fallo.
`request_id` UUID permite correlación y reintentos idempotentes por titular. Un
UUID reutilizado con otro cuerpo/operación devuelve 409. El HTTP 200 transporta
el estado funcional `complete`, `partial`, `needs_clarification`, `unsupported`
o `error`; hay que examinar ese estado.

El endpoint compuesto llama a Data e Insights por HTTP, también cuando comparten
proceso. Después adjunta el texto mediante el MCP de composición sin otra ronda
LLM: las gráficas no cambian. Los IDs de evidencia se resuelven por su huella
canónica aunque Insights los haya renombrado. Funciona con Insights remoto;
ambos servicios deben reconocer la identidad Bearer que se delega.

Plazo HTTP máximo: 55 s; el endpoint compuesto reserva 8 s para publicación.
Se limita a ocho turnos de analista, diez tools, dos recuperaciones de datos,
dos revisiones visuales, 220 hechos y 8 MiB de evidencia. Cold starts o fallos
externos pueden producir timeout: no se garantiza un informe por petición.
Las páginas/revisiones están en memoria, con TTL; exportar HTML para conservarlas.

## Ejecución

```powershell
.\.venv\Scripts\python.exe -m inside_game.agents_cli --port 8085
```

Reutiliza la configuración privada existente y Beam Free de OpenCode Go con
`INSIDE_GAME_OPENCODE_FREE_ONLY=1`. Se verifica precio cero antes de inferencia;
no hay fallback de pago, recarga ni cambio de facturación. `INSIDE_GAME_DATA_AGENT_URL`
y `INSIDE_GAME_INSIGHTS_AGENT_URL` separan procesos; destinos remotos exigen HTTPS.

QA con trazas optativas locales (no usar el servidor de trazas para tráfico privado
ajeno a la prueba):

```powershell
python scripts/qa_insight_trace_server.py --port 8088 --output-dir .temp/insights/analyst-qa
# En otra terminal:
python scripts/qa_sports_analyst.py
```

Las trazas incluyen instrucciones y llamadas observables de los tres agentes,
sin credenciales ni razonamiento interno. No constituyen una prueba de cobertura
de todas las familias, partidos o interpretaciones posibles.


## Representación de hechos topológicos

Los valores Betti, intervalos y retiradas virtuales se conservan como hechos
individuales con escala, población y alcance. Las notas de interpretación del
método son contexto y límites, no hallazgos citables. El contexto del modelo
comparte los metadatos repetidos mediante `scope_catalog`; no se eliminan hechos
para ocultar un exceso de contexto. Si se rebasa el límite se devuelve un error.

Los placeholders conocidos añaden automáticamente sus citas omitidas. Cuando
el proveedor codifica dos veces campos JSON de `finish_analysis`, se decodifican
sólo si son JSON completo del tipo esperado; no se convierten cifras ni se
corrigen argumentos de consulta. La traza registra esa normalización. No se
interpreta código ni se aceptan payloads truncados.

Una regla adicional rechaza asignaciones explícitas de fases tácticas a partir
de referencias exclusivamente geométricas. Esta regla no pretende comprender
todas las formulaciones lingüísticas: la revisión humana sigue siendo necesaria.

Para reproducir el flujo habitual con Data previo al analista:

```powershell
python scripts/qa_sports_analyst.py --data-first --output-dir .temp/insights/analyst-demo
```

Los JSON `*.request.json` de la demostración incluyen también la petición avanzada
con `persistent_structure`, `node_robustness` y `space_partition`, reutilizando
la evidencia original. La traza conserva los turnos y sus schemas efectivos.


## Demostración verificada

La exportación local `.temp/insights/analyst-demo/index.html` reúne tres páginas,
texto y trazas. Data previo + primera página: 32,010 s; nueva lectura con datos
reutilizados: 19,564 s; topología avanzada con datos reutilizados: 24,925 s.
Se verificaron 51 hechos contra sus campos originales y la suite pasó 418 tests.
No es una garantía de latencia ni una validación deportiva de los datos sintéticos.
Los fallos previos y los rechazos de contrato se conservan en el informe.

[Verificación estructurada](sports-analyst-verification.json).

Para repetir las tres páginas de la exportación, con el servidor de trazas
activo y el archivo avanzado extraído del ZIP:

```powershell
python scripts/qa_sports_analyst.py --data-first --advanced-request .temp/insights/analyst-demo/advanced-topology.request.json --output-dir .temp/insights/analyst-demo
python -m pytest -q --junitxml=.temp/insights/analyst-demo/pytest.xml
python scripts/build_sports_analyst_bundle.py .temp/insights/analyst-demo
```

La respuesta de análisis sigue disponible como `partial` si falla la publicación
final del HTML. Las comparaciones basadas sólo en tablas exponen las primeras
diez filas con su alcance explícito y se marcan parciales si hay más; no se
presentan como un análisis de todas las entidades.
