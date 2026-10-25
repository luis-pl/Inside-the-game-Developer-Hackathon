# Composición visual de los insights

Las treinta familias comparten piezas paramétricas, paleta e identidad. El
agente selecciona recetas y parámetros; el renderer construye SVG y HTML con
código de la biblioteca. No pide al modelo escribir una página completa.

## Separación de las piezas

| Nivel | Implementación | Entrada y responsabilidad |
|---|---|---|
| Fundamentos | `identity.py`, tokens CSS de `templates.py` | Paleta por ID de equipo, nombres y dorsales de `get_match_context` |
| Átomos | `atoms.py` | Texto escapado, número, estado, punto, vector y marcas elementales de cancha |
| Moléculas | `molecules.py` | Leyenda color + nombre, lectura numérica, tabla, notas y enlaces a evidencia |
| Organismos | `charts.py`, `organisms.py` | Datos normalizados → mapa, red, cronología, serie, barcode, replay, sección completa |
| Templates | `templates.py` y composición de `pages.py` | Distribución responsive y slots de ancho completo o media página |
| Páginas | `ReportSpec` → `render_report` | Selección y orden concretos, evidencia original y HTML autocontenido |

`adapters.py` valida y transforma la evidencia. No decide colores ni layout.
Los organismos reutilizan moléculas y átomos; las páginas coordinan las escalas
de mapas térmicos con la misma unidad. Cambiar la composición no requiere
cambiar consultas SQL, CSS, JavaScript ni escribir nuevos componentes.

## Parámetros de presentación

Ejemplo de plan para el MCP, con IDs de evidencia ya descubiertos por su tool
`list_insights`. Los IDs de este ejemplo son ilustrativos: deben sustituirse
por los del resultado real del agente de datos.

```json
{
  "title": "Espacio y circulación",
  "template_id": "match_overview",
  "teams": [
    {"team_id": 1, "color": "#2463bc"},
    {"team_id": 2, "color": "#bf402e"}
  ],
  "blocks": [
    {
      "id": "red_local",
      "insight_id": "passing_network",
      "evidence_ids": ["red_equipo_1", "pases_equipo_1"],
      "parameters": {"team_id": 1},
      "visual": {"span": "half", "min_edge_weight": 3}
    },
    {
      "id": "posesiones",
      "insight_id": "sequence_explorer",
      "evidence_ids": ["posesiones_partido"],
      "visual": {"span": "full"}
    },
    {
      "id": "espacio",
      "insight_id": "space_partition",
      "evidence_ids": ["voronoi_600s", "tracking_600s"],
      "parameters": {"period": 1, "time_ms": 600000},
      "visual": {"span": "full", "show_labels": true, "show_legend": true}
    }
  ]
}
```

Cada bloque conserva sus filtros de datos en `parameters`. `visual` admite
`span: auto/full/half`, `show_labels`, `show_legend` y `min_edge_weight` (1–100).
El umbral sólo oculta enlaces del dibujo; no altera la red ni sus métricas.
El pie de la figura declara el umbral. El orden de `blocks` es el orden de lectura.
La paleta es compartida por campos, redes, curvas, áreas y replay. Los colores
aceptan únicamente hexadecimal de seis dígitos. Los nombres y dorsales se
obtienen del contexto; los colores son configurados, no oficiales.

## Lecturas y límites

- Redes: posición media de orígenes de pases completados y destinos de recepción
  con equipo y alcance compatibles. Tamaño del nodo por participación y grosor
  por volumen. Si faltan posiciones para algún nodo, toda la red se declara
  esquemática. No representa la posición media del tracking.
- Tiros: equipo por color, gol por doble anillo, parada rellena, resto hueco.
  El área incorpora xG cuando existe, con tamaño mínimo para lectura. Sin xG se
  usa tamaño fijo. Los eventos se muestran en referencia de ataque de cada equipo.
- xG: acumulado separado por equipo y período. No se suman períodos en una curva
  continua ni se rellenan valores ausentes. El sintético sigue marcado ilustrativo.
- Posesiones: tramos entre primer y último evento registrado, sin rellenar huecos;
  las tarjetas resumen secuencias. No se presentan como porcentaje oficial de tiempo.
- Ocupación: suma de jugadores en una celda, unidad s·jugador y escala compartida.
  Se rechaza superponer mapas de distintos participantes o alcances en un bloque.
- Voronoi: celdas por equipo y jugadores desde tracking del mismo instante.
  El centro de una celda nunca se convierte en una posición de jugador.
- Rupturas: enlaza `get_line_breaks` con los IDs originales de `get_passes`.
  Las rupturas geométricas no se presentan como anotación `through_ball`.
- Hodge: red esquemática y composición de energía. Persistencia: H0/H1, eje de
  distancia y censura a 40 m. Se conservan sus límites científicos.
- Replay: colores y dorsales coherentes; reloj 1×, sin interpolación ni balón
  inventado. Tablas, evidencia y notas permanecen disponibles sin conexión.

## Referencias utilizadas

Las referencias guían el lenguaje gráfico; no se copiaron sus activos ni se
atribuyen a nuestros cálculos las métricas propietarias de otros productos.

- [WC26, Data Portraits](https://wc26.bogachev.fr/): inspiración para jerarquía de
  partido, identidad cromática y coordinación de distintas lecturas temporales.
- [Football Decoded](https://www.footballdecoded.com/visualizations): ejemplos de
  redes, tiros, mapas espaciales y fichas; referencia para una biblioteca variada.
- [DeepMoire](https://www.deepmoire.com/projects/automated-football-data-visualization/):
  composición automática de vistas y consistencia de color entre gráficos.
- [futi](https://futi.live/): referencia de secuencias y visualizaciones compartibles.
- [Footovision](https://www.footovision.com/visualizing-positioning-and-player-decisions-the-innovation-of-dynamic-pitch-control):
  distingue partición geométrica de control dinámico. Nuestro Voronoi sigue
  expresando cercanía; no calcula un modelo probabilístico de control.

## Verificación

Ejecución con quince respuestas nuevas de la API del partido sintético `900001`:
quince bloques disponibles, 47 rupturas situadas con sus pases originales,
redes con posiciones de pase y ninguna credencial en el HTML. Recuperación:
3,35 s con el servicio disponible; render final: aproximadamente 46 ms.
La primera llamada recibió 503 y el reintento posterior respondió 200; no se
promete el mismo tiempo ante arranques en frío, fallos o fuentes más grandes.

La suite completa pasó 183 pruebas. El MCP por stdio descubrió cinco tools,
creó las treinta piezas individualmente, validó el plan y devolvió una página
compuesta con recursos HTML. Se verificaron escritorio, móvil,
filtro y replay con 22 jugadores; no se observó desbordamiento horizontal a
390 px de viewport solicitado. Las mediciones y límites están en
[insights-verification.json](insights-verification.json).

La biblioteca y el MCP de composición están implementados. La conversación del
agente de insights y la orquestación A2A siguen pendientes; este cambio no las
declara terminadas ni despliega un servicio nuevo en Azure.
