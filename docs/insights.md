# Biblioteca de treinta insights y renderer HTML

Las veinte familias aprobadas y las diez extensiones investigadas tienen recetas
y adaptadores ejecutables. El renderer es determinista: no genera código con un
LLM, no accede a SQL y no necesita red. El agente conversacional de insights y su
comunicación HTTP están implementados en [insight-agent.md](insight-agent.md).
El MCP de composición ofrece cinco tools y recursos HTML.

## Archivos y metodología atómica

| Archivo en `src/inside_game/insights/` | Función |
|---|---|
| `catalog.json`, `catalog.py` | Treinta recetas, fuentes, operaciones y limitaciones |
| `contracts.py` | Planes tipados, parámetros cerrados, evidencia y estados |
| `adapters.py` | Evidencia MCP → datos visuales; validación de filtros, páginas y alcance |
| `advanced.py` | Diez cálculos locales investigados |
| `atoms.py` | Texto escapado, números, estados, puntos y vectores |
| `identity.py` | Identidades y paleta estable por equipo; dorsales del contexto del partido |
| `molecules.py` | Métricas, leyendas/avisos, tablas y enlaces de evidencia |
| `charts.py`, `organisms.py` | Campo, red ponderada, series por período, cronología, comparación, secuencias, barcode, replay y fuentes |
| `templates.py` | CSS/JS locales y layouts responsive |
| `pages.py` | Template + bloques + datos originales → HTML autocontenido |
| `mcp_server.py` | Descubrimiento, descripción, validación, render y lectura del recurso |
| `demo.py` | Galería con escenario SINTÉTICO ilustrativo de componentes |

Los cinco templates son resumen de partido, ficha de jugador, comparación de
entidades, episodio táctico e informe libre. Los primeros cuatro distribuyen
organismos en dos columnas en pantalla ancha y una en móvil; el informe libre
mantiene lectura vertical. Cada página es una instancia concreta de su template.

El refinamiento visual, sus referencias y los parámetros de presentación están
en [insights-visual-design.md](insights-visual-design.md).

## Informe compuesto con un partido de la API

```powershell
.\.venv\Scripts\python.exe scripts/build_insights_report.py --match-id 900001 --output .temp/insights/match-900001.html
.\.venv\Scripts\python.exe -m http.server 8083 --bind 127.0.0.1 --directory .temp/insights
```

Abre <http://127.0.0.1:8083/match-900001.html>. Incluye quince bloques a partir
de consultas nuevas a la API existente: tiros, xG por período, secuencias de
posesión, redes de pases de ambos equipos, trayectorias, ocupación, Voronoi,
estructura, replay, persistencia, Hodge y rupturas geométricas de líneas.
El partido `900001` es **sintético**. El xG es ilustrativo, no calibrado.

El script usa la configuración privada existente mediante `DashboardConfig`;
no lleva claves en argumentos, manifiestos o HTML. Sigue los cursores de las
consultas paginadas, valida los contratos registrados y rechaza redirecciones.
Si Azure rechaza una consulta, interrumpe la exportación. El script es una
demostración de recuperación y composición determinista; no llama a un modelo.

El informe exportado funciona sin conexión. Para componer otra selección utiliza
`ReportPlan` con sus `blocks`, `parameters`, `visual` y `teams`; conserva únicamente
las referencias de evidencia necesarias. El MCP de insights acepta ese mismo
plan, resuelve la evidencia confiable del anfitrión y devuelve un recurso HTML.

## Ver la galería

Desde la raíz del repositorio:

```powershell
.\.venv\Scripts\python.exe -m inside_game.insights.demo
.\.venv\Scripts\python.exe -m http.server 8083 --bind 127.0.0.1 --directory .temp/insights
```

Abre <http://127.0.0.1:8083/gallery.html>. El selector permite explorar cada familia.
La galería es un fixture ilustrativo de catorce jugadores, marcado SINTÉTICO;
no es un partido de Azure ni del Mundial. Su propósito es probar composición,
contratos y visualización, no realismo futbolístico.

El archivo también funciona abierto directamente y sin conexión. Los botones
permiten imprimir y descargar los datos incluidos. El replay conserva muestras
originales, ausencia de balón y escala 1× en tiempo real, sin interpolar.

## Exportar la respuesta del agente de datos

```powershell
.\.venv\Scripts\python.exe -m inside_game.insights --data-result .temp/prueba-agente.json --insight shot_map --output .temp/insights/tiros.html
```

Para varias recetas o parámetros usa `--manifest informe.json --output informe.html`.
Un manifiesto offline tiene `title`, `template_id`, `blocks` y `evidence`.
Los bloques usan `id`, `insight_id`, `evidence_ids` y `parameters`. No aceptan
HTML, SQL, URLs ni JavaScript. El esquema exacto es `ReportSpec.model_json_schema()`.
La galería genera un ejemplo completo en `.temp/insights/gallery.manifest.json`.

Los parámetros incluyen equipo/jugador, período e instante, orientación,
defensores/medios/portero declarados, epsilon de 5/10/15/20 m y modo Hodge.
Los roles aportados manualmente son una selección explícita del anfitrión;
no se presentan como roles anotados por la fuente.

## MCP para el agente de insights

```powershell
.\.venv\Scripts\python.exe -m inside_game.insights.mcp_server --evidence-file .temp/prueba-agente.json
```

El transporte es stdio local. El anfitrión inicia una instancia con la evidencia
autorizada de una solicitud. El modelo descubre IDs/operaciones/cobertura y envía
un `ReportPlan` pequeño; no puede reemplazar la evidencia con cifras inventadas.

- `list_insights`: catálogo de treinta y resumen de la evidencia disponible.
- `describe_insight`: operaciones, parámetros y límites de una receta.
- `validate_report`: compatibilidad del plan y estado por bloque.
- `render_insight`: una pieza individual con la misma estructura paramétrica
  de un bloque (`insight_id`, `evidence_ids`, `parameters`, `visual`, `teams`).
- `render_report`: URI de recurso, bytes, tiempo y estados. El HTML se obtiene
  mediante `resources/read`, sin reenviar todo el documento al contexto del modelo.

El anfitrión conserva la responsabilidad de guardar y mostrar el recurso. No hay
rutas de archivo, destinos de red ni claves en argumentos del modelo. Los recursos
son privados de esa instancia stdio, limitados a cuatro documentos y 32 MiB;
desaparecen al terminar el proceso. No se publicó un nuevo endpoint HTTP/Azure.

### Contrato de integración con un agente

1. El anfitrión obtiene un `DataResult` del agente de datos y conserva su lista
   original `evidence`. Inicia `create_server(evidence)` en Python o el comando
   stdio anterior con ese archivo. Cada instancia contiene la evidencia de esa
   solicitud; para otra recuperación, el anfitrión inicia otra instancia.
2. El modelo llama `list_insights` para descubrir las treinta recetas y los IDs
   de evidencia disponibles; `describe_insight` devuelve requisitos y esquemas.
3. Para una pieza llama `render_insight`. Para una página elige varios bloques,
   comprueba `validate_report` y llama `render_report`.
4. El anfitrión obtiene el HTML usando `resources/read` sobre `resource_uri` y lo
   guarda o muestra. El HTML no tiene que volver al contexto del modelo.

`valid` comprueba compatibilidad; `ready` sólo es verdadero cuando todos los
bloques están disponibles. Un plan puede ser válido pero contener un bloque
`unavailable` por falta de xG o roles. El agente debe inspeccionar los estados,
pedir la evidencia que falta o conservar explícitamente esa ausencia.

Ejemplo de argumentos de `render_insight`:

```json
{
  "insight_id": "passing_network",
  "evidence_ids": ["ID_DE_RED", "ID_DE_PASES"],
  "parameters": {"team_id": 1, "period": 1},
  "visual": {"min_edge_weight": 3},
  "teams": [{"team_id": 1, "color": "#2463bc"}]
}
```

Los IDs se sustituyen por los devueltos por `list_insights`. Los parámetros no
son coordenadas inventadas: seleccionan y transforman evidencia confiable. Las
treinta recetas se anuncian como valores permitidos en el esquema de la tool.
No hay treinta tools duplicadas ni una llamada por punto o átomo.

Configuración de ejemplo para un cliente que use `mcpServers` (sustituir rutas
absolutas; `command` apunta al Python del entorno instalado):

```json
{
  "mcpServers": {
    "inside-game-insights": {
      "command": "<REPO>/.venv/Scripts/python.exe",
      "args": ["-m", "inside_game.insights.mcp_server", "--evidence-file", "<DATA_RESULT_ABSOLUTO.json>"],
      "cwd": "<REPO>"
    }
  }
}
```

Para probar exactamente el transporte que inicia un cliente de agente:

```powershell
.\.venv\Scripts\python.exe scripts/verify_insights.py --stdio
```

La prueba descubre las cinco tools, crea cada una de las treinta piezas por
separado, lee sus recursos HTML y compone una página con todas. Usa un fixture
sintético local identificado, sin consumir un modelo ni consultar Azure.

## Fidelidad y límites

- Cada bloque muestra estado, método, procedencia y referencias a evidencia.
- El JSON original se conserva dentro del HTML; los previews visibles están acotados.
- No se suman resúmenes repetidos por página. Faltar páginas produce `partial`.
- No se mezclan partidos o procedencias dentro de una misma geometría.
- xG desconocido produce `unavailable`; no se transforma NULL en cero.
- Los eventos se dibujan en referencia del equipo actuante; tracking es fijo.
  La alineación para métricas de pase exige dirección y tolerancia explícitas.
- No se infieren roles de una camiseta. La geometría de una ventana indica qué
  snapshot representa; no convierte una imagen en resumen de todo el período.
- HTML con CSS/SVG/JS incluidos, CSP sin conexiones externas y texto/JSON escapados.
- Límite de entrada 8 MiB, salida 16 MiB, cuarenta bloques por informe y hasta
  trescientos snapshots por bloque de comparación topológica.

Las implementaciones EFI y de papers son adaptaciones locales con sus límites,
documentadas en [la investigación](insights-research.md). No se afirma que las
treinta familias tengan cobertura en cada fuente o que se hayan validado contra
resultados oficiales del Mundial.

## Verificación y tiempos

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_insights.py -q
.\.venv\Scripts\python.exe scripts/verify_insights.py
```

El verificador recorre las treinta recetas y el MCP, conserva la galería y mide
diez renders locales. Con `--data-result RUTA` repetido acepta resultados originales
del agente y produce `agent-report.html`; `--team-id ID` habilita derivados del tracking.

El benchmark mide ensamblado con evidencia ya disponible, sin LLM, API ni SQL.
No implica menos de un minuto para toda la conversación. El agente de datos
mantiene su deadline independiente. Informe medido: `docs/insights-verification.json`.
