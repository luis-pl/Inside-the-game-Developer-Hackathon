# Agente de insights

Convierte una pregunta o una intención estructurada en un informe HTML y una
respuesta JSON. Vive en `src/inside_game/agents/insights_agent/`;
`agents/dashboard_builder.py` lo reexporta.

```text
AskRequest { question | intent, previous? }
  pregunta  → planificador (LLM) → aclaración / rechazo / MODEL_UNAVAILABLE
  intención → resolvedor → datos (A2A o local) → compositor + MCP de insights
AskResult
  answer      InsightAnswer (JSON pequeño, ~10 KB)
  report_html informe autocontenido (1–9 MB), aparte
```

El LLM sólo interpreta texto. Plantillas, recetas posibles por fuente,
parámetros, ventanas, consultas, guardián y resumen son deterministas.

## Uso

```powershell
# Con el agente de datos por A2A (docs/a2a.md); sin --data-agent-url llama a la API.
.\.venv\Scripts\python.exe -m inside_game.agents.insights_agent --data-agent-url http://127.0.0.1:8010 `
  --intent '{"template_id": "match_overview", "match_id": 900011}' `
  --question "¿Y solo el segundo tiempo?"
```

Con `--insights-agent-url http://127.0.0.1:8020` la conversación va al agente
de insights expuesto por A2A ([a2a.md](a2a.md)).

Cada `--intent`/`--question` es un turno de la misma conversación: `answer.next`
alimenta el siguiente. Guarda `NN-<tipo>.json` y, si hay informe, `NN-<tipo>.html`.
`--question` sólo usa un modelo si `INSIDE_GAME_MODEL_PROVIDER` está configurado
explícitamente; si no, responde `MODEL_UNAVAILABLE` (no se elige modelo por defecto).

## Página web local

```powershell
.\.venv\Scripts\python.exe -m inside_game.agents.insights_agent.web --port 8030 --data-agent-url http://127.0.0.1:8010 --azure-model gpt-5-mini-1
```

Abre <http://127.0.0.1:8030/>. La página se construye con el **diseño atómico de
la librería de insights**, el mismo de los informes:

| Nivel | Piezas de la web |
|---|---|
| Átomos | `tag` (procedencia), `status`, `text` (todo texto escapado) |
| Moléculas | `answer_card`, `clarification_card`, `notice_card`, `source_tag`, `chat_message` |
| Organismos | `masthead`, `conversation`, `ask_panel` (preguntar / elegir informe), `about`, `report_canvas` |
| Template | «espacio de trabajo»: `WORKSPACE_CSS` + `WORKSPACE_JS` sobre la base `CSS` + `JS` |
| Página | `render_workspace()`; el lienzo usa `report_parts()`, las piezas del informe |

En cada petición el servidor compone con esas piezas la respuesta de la
conversación y el lienzo, con **los mismos organismos que el informe exportado**,
sin iframe. El navegador sólo coloca los fragmentos y llama a
`initInsightsReport(lienzo, datos)`. `render_report` sigue produciendo el mismo
HTML autocontenido; sólo cambió su script, ahora inicializable por zona.

Dos formas de pedir: **Preguntar** (texto, usa el modelo elegido en el comando;
cada pregunta consume tokens) y **Elegir informe** (partido, tipo, equipo, parte y
minuto o piezas; no usa el modelo). La respuesta muestra título, fuente (datos
reales o sintéticos), piezas mostradas, piezas no disponibles con su motivo y las
decisiones del agente. `#informe=<id>` conserva el lienzo al recargar mientras
siga entre los 12 últimos; «Abrir en otra pestaña» abre el informe exportado.

**Conversación continua.** Mientras no se pulse «Nueva conversación», el cliente
envía `append_to` con el informe actual. Si la nueva respuesta es del mismo
partido y los mismos equipos (según el contexto de la evidencia), sus piezas se
suman al informe en vez de reemplazarlo, **las nuevas arriba** (lo último que se
pidió es lo primero que se ve): la respuesta dice «ahora tiene N piezas»,
una pieza idéntica no se repite y la misma receta con otros parámetros se añade
con título distinto (p. ej. «· 2.ª parte»). Otro partido empieza un informe
nuevo. Los IDs de evidencia de cada petición chocan entre sí, así que los de las
peticiones añadidas llevan el prefijo `t2-`, `t3-`… (`agents/insights_agent/merge.py`).
El informe anterior sigue disponible por su enlace. Los informes combinados se
guardan con su manifiesto (hasta 12 en memoria).

- Sólo loopback; comprueba `Host` y `Origin`, exige JSON y atiende una petición a
  la vez, para que otra web no pueda gastar tokens desde el navegador.
- CSP: scripts y estilos sólo como archivos (`/assets/insights.js` y `.css`);
  `style-src-attr 'unsafe-inline'` únicamente para los colores de equipo de los
  organismos.

## Contrato

- `AskRequest`: exactamente uno de `question` o `intent` (`InsightIntent`), y
  `previous` opcional.
- `InsightAnswer`: `kind` (`report`, `clarification`, `declined`, `error`),
  `summary`, `intent`, `clarification`, `labels` (partido, equipos, jugador,
  proveedor, `synthetic`), `blocks` (estado, avisos y métricas con claves
  estables), `discarded` con motivo, `decisions`, `issues`, `has_report`,
  `next` y `timings_ms`.
- Sin sesiones en el servidor: el cliente devuelve `answer.next` tal cual. Lleva
  la intención anterior (seguimientos) o la aclaración pendiente con la pregunta
  que la originó, para que "el segundo" se entienda.
- Las métricas se entregan sin el ID de consulta (`q12.tackles_won` →
  `tackles_won`; si dos consultas chocan, `operación.clave`): iguales por A2A y en
  local. Pensadas para el analista u otro narrador.
- Si una intención trae `player_id` y un `team_id` que no es el de ese jugador,
  prevalece el equipo del jugador. `decisions.team_adjusted_from` y el resumen
  explican el ajuste; no se genera un informe enfocado en el equipo equivocado.

## Resumen

Determinista y sin análisis deportivo: título, fuente (datos SINTÉTICOS o reales
anonimizados/seudonimizados y proveedor), piezas mostradas, piezas no mostradas
con su motivo, equipo protagonista por defecto e instante analizado o ajustado.
La redacción analítica corresponde al analista.

## Qué decide el agente para que el informe sea útil

- **Momento del episodio táctico.** Sin instante pedido, ancla en un gol del
  equipo protagonista; si no hay, en su tiro de mayor xG; si la fuente no anota
  xG, en el tiro más cercano a portería (distancia al centro de la portería, campo
  de 105×68 m). Prueba hasta 5 momentos y usa el primero con todos los jugadores
  posicionados; el resumen dice el criterio. Un instante pedido por el usuario
  nunca se sustituye.
- **Ficha de un portero.** La fuente anota quién es el portero; se descartan
  `shot_map`, `ball_progression` y `defensive_actions` (saldrían en cero) con el
  motivo en la respuesta.
- **Sin cifras vacías.** Las métricas sin valor y las categorías `Unknown…` de la
  fuente no se muestran como cifras (ni en los tooltips de los tiros). Tampoco
  el recuento `total` de filas de la respuesta, que no es una métrica.
- **Ceros que no son ceros.** El perfil de cada fuente (`source_profiles.json`)
  guarda, por receta de eventos, las métricas que valen cero (o vienen vacías) en
  **todos** los partidos medidos (p. ej. duelos aéreos o 50/50 en Metrica; goles y tiros a
  puerta en SkillCorner). Esas cifras en cero se omiten; con un valor distinto de
  cero se muestran. Hace falta medir al menos 2 partidos por fuente: al
  regenerar los perfiles con `--write-profiles`, ejecuta la matriz sobre todos los
  partidos (con uno por fuente la clave se vacía). El perfil llega también al
  render final (`create_server(..., render_options=…)`), no sólo al guardián.
- **La respuesta en una frase.** Bajo la pregunta de cada pieza, una frase en
  negrita con la cifra que la contesta (`insights/headlines.py`, una función por
  receta, 30 en total): «Mediana de 47 s para recuperar el balón tras perderlo
  (media 69 s, máximo 253 s; 30 recuperaciones).». Se calcula de los datos de la
  pieza, sin modelo; si una pieza no tiene qué decir, no muestra frase. Una prueba
  recorre las 30 recetas de la galería y exige frase limpia en español.
- **Pases con coordenadas.** La API sólo da longitud, pases progresivos y entradas
  al último tercio si *todos* los pases tienen origen y destino; en SkillCorner
  los fallidos no tienen destino y el resumen devuelve `null`. El informe calcula
  entonces esas tres cifras con los mismos criterios sobre los pases que sí tienen
  coordenadas, y las rotula «(sólo con coordenadas)».
- **Etiquetas en español y datos por equipo.** `insights/labels.py` traduce
  métricas, categorías de resultado, partes del cuerpo, tipos de evento y
  encabezados de tabla; los carriles se llaman «Carril 1 (banda)…» sin decir
  izquierda o derecha, porque el sentido de la coordenada depende de la fuente.
  Las piezas de partido (tiros, pases, acciones defensivas, con balón) añaden una
  tabla «Por equipo» con una fila por equipo, calculada de los eventos; las
  columnas sin datos no aparecen.
- **Cronología.** Grafica los eventos registrados por equipo en tramos de 5
  minutos, con una línea por equipo, y marca bajo el eje los goles, cambios y
  tarjetas que la fuente registra (una franja por equipo, con tooltip); debajo, la
  misma información en una lista plegada. El último tramo de cada período suele ser
  parcial y se ve más bajo.
- **Preguntas por pieza.** Cada receta tiene su pregunta en el catálogo; el
  planificador también la recibe.

## Tiempo de respuesta (objetivo: ≤ 10 s)

25 de octubre, informe por intención (sin modelo), contra la API de Azure:

| Informe | Antes | Ahora |
|---|---|---|
| match_overview (8–10 piezas) | 17–24 s | 3,5–5,5 s |
| player_dossier | 3–6 s | 4,4 s |
| tactical_episode | 5,6–6,6 s | 2,3 s |

La causa era el cliente de datos: un espaciado fijo de 0,6 s entre consultas
(~40 por resumen) cuando la API tarda 0,1–0,2 s por consulta. Ahora respeta la
ventana deslizante de 120/min con ráfagas (tope de 110), lanza en paralelo las
consultas independientes (máx. 3 a la vez; la API admite 4) y mantiene en orden
las páginas de una misma consulta. El cuello restante es la cadena de ~21 páginas
de `get_events` de la cronología (200 eventos por página).

Lo que todavía puede romper los 10 s:

- **Arranque en frío.** Tras un rato sin uso la base serverless se pausa; la
  primera consulta tardó 77 s en reanudar. Ahora se sondea cada 3 s, pero la
  reanudación en sí no se acorta. Mantenerla despierta con consultas periódicas
  gasta cómputo: decisión de presupuesto, no se hizo.
- **Ventana de 120/min compartida.** Varios informes seguidos (o varios procesos
  con la misma clave) llegan al límite y la API pide esperar 60 s; una prueba A2A
  tras tres informes consecutivos tardó 66 s, probablemente por eso (no se
  confirmó).
- **Preguntas en texto.** El planificador con modelo tarda de 5 a 17 s por
  pregunta (mediana ~10 s) antes de empezar el informe: en texto no se llega a
  10 s. «Elegir informe» no usa modelo.

## Verificación

55 pruebas del agente y sus piezas (`tests/test_insights_agent*.py`,
`test_evidence_client.py`, `test_a2a_*.py`) sin red ni inferencia. El 25 de
octubre, una conversación de cuatro turnos por A2A contra Azure: ficha de jugador
(SkillCorner, 5 piezas y 2 descartes), resumen (Metrica, 9 piezas, xG descartado),
pregunta sin modelo (`MODEL_UNAVAILABLE`, conserva la intención anterior) y
episodio táctico (sintético, 8 piezas). Respuesta de 10 KB frente a 5,4 MB de HTML.

## Evaluación del planificador con modelo real

25 de octubre, `gpt-5-mini-1` en el recurso Azure del usuario (crédito gratuito),
API Responses con llamada a herramienta obligatoria y razonamiento bajo. Una sola
pasada de las 15 preguntas de `tests/fixtures/insights_planner_cases.json`,
deteniéndose ante el primer error de modelo (no hubo ninguno). Informe:
[insights-planner-evaluation.json](insights-planner-evaluation.json).

- 14 de 15 aciertos; mediana 5,3 s por pregunta; 113.986 tokens en total
  (unos 6.000 por pregunta, 12.000 cuando consulta también la plantilla).
- Resolvió nombres, dorsales (incluida la trampa "dorsal 10" ≠ "Jugador 10"),
  minuto del período y del reloj, fechas, seguimientos, ambigüedad, fuera de
  alcance y xG en una fuente sin xG.
- El caso fallido (`overview_by_name`, "el primer partido de Metrica") pidió
  aclaración con las dos opciones. Las fechas de Metrica son desconocidas
  (1900 es un marcador), así que la pregunta es ambigua. La expectativa del caso
  se corrigió a `clarification`; con ella el resultado de aquella pasada habría
  sido 15 de 15 (sin repetir la evaluación).
- El mensaje de rechazo ofreció "probabilidades oficiales", una capacidad que el
  sistema no tiene. Se añadió la regla 7 al prompt (no ofrecer alternativas
  inexistentes). La evaluación corresponde al prompt anterior (`1e3c9f47…`); el
  actual (`56f11c13…`) no se ha vuelto a evaluar para no gastar tokens.

### Segunda pasada con el prompt actual

25 de octubre, mismo modelo y casos, prompt `56f11c13…` (con la regla 7) y la
expectativa corregida de `overview_by_name`. Una sola pasada, sin errores de
modelo: **15 de 15**; mediana 9,0 s; 121.948 tokens. Informe:
[insights-planner-evaluation-2.json](insights-planner-evaluation-2.json).

- `overview_by_name` aclaró con las dos opciones, como se espera.
- El rechazo de `out_of_scope` ya no ofrece alternativas inexistentes: sólo
  resúmenes, comparaciones e informes tácticos de partidos jugados.
- La primera pregunta tardó 99,6 s; no se midió si fue la API de datos o el
  modelo (probable arranque en frío, sin confirmar). Es un valor atípico: no
  mueve la mediana, que subió de 5,3 s a 9,0 s respecto a la primera pasada. La
  causa del aumento no se investigó para no gastar más tokens.
- 15 casos con un partido por fuente no equivalen a QA del corpus completo.

### Tercera pasada con el catálogo ampliado

25 de octubre, mismo modelo y casos, prompt `0b1a3d33…`: las diez recetas que no
tenían pregunta en el catálogo ahora la tienen y el planificador las recibe.
Una sola pasada, sin errores de modelo: **15 de 15**; mediana 10,3 s; 132.748
tokens (+10.800 frente a la segunda pasada; no se investigó la causa, el prompt es
más largo). Informe:
[insights-planner-evaluation-3.json](insights-planner-evaluation-3.json).

Límite: ninguno de los 15 casos pide una de esas diez recetas, así que esta pasada
muestra que el cambio no empeora lo anterior, no que el planificador las elija
mejor. Para medirlo habría que añadir casos (por ejemplo, «¿por qué carril
entraron al último tercio?»), lo que gasta más tokens.

### Cuarta pasada: catálogo precargado y razonamiento bajo

26 de octubre, mismo modelo, prompt `c586a0e8…`. Tres cambios: el resultado de
`list_matches` llega ya en la conversación (un turno de modelo menos); una regla
nueva —una pregunta sobre UNA métrica entre los dos equipos («¿quién tiró más?»)
es `custom_report` con esa receta, no la comparación de siete piezas—, con un
caso nuevo en el fixture (16 casos); y `INSIDE_GAME_REASONING_EFFORT=low`, que la
web aplica por defecto al elegir `--azure-model`.

| Pasada (16 casos) | Aciertos | Mediana | Tokens |
|---|---|---|---|
| Razonamiento `medium` (por defecto del proveedor) | 16 de 16 | 10,0 s | 114.176 |
| Razonamiento `low` | **16 de 16** | **5,1 s** | **94.048** |

Informe: [insights-planner-evaluation-4.json](insights-planner-evaluation-4.json).
Las pasadas 2 y 3 son de 15 casos y se ejecutaron sin fijar el razonamiento, es
decir, con el `medium` por defecto del proveedor; la primera dice «bajo» y no se
puede comprobar aquí. Cada cifra es una sola pasada. La mediana no incluye el informe: preguntas escritas, de
extremo a extremo, quedan en torno a 5 s del planificador más 2–5 s de datos.

El modelo no queda seleccionado por defecto: el agente sólo lo usa si
`INSIDE_GAME_MODEL_PROVIDER` y el despliegue se configuran explícitamente.
