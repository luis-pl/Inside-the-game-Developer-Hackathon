# Revisión de agentes y soporte multilingüe — 27 de octubre de 2026

**Actualización:** este documento registra la primera fase. La siguiente fase
incluye inferencias reales, consultas, carga progresiva de herramientas,
compactación y 546 pruebas locales. Sus resultados y límites están en
[Pruebas de calidad de agentes](agent-quality-2026-10-27.md); reemplazan el alcance
inicial de validación y catálogo completo en cada turno descrito abajo.

Se actualizaron las referencias remotas y se contrastó `main` (`5852754`) con
`origin/experimento/agentes-nim` (`342d453`), la rama que introduce las
optimizaciones experimentales. También se identificaron las mejoras previas de
`feature/conversation-report-and-faster-planner`, `feature/insights-agent-a2a`,
`feature/ollama-provider` y la integración de Beam. Los cambios de esta revisión
se aplican al árbol local de `main`, conservando las modificaciones preexistentes.
No se hizo merge, cherry-pick, push, despliegue ni cambio de proveedor.

## Hallazgos de la rama experimental

Estos comportamientos dependen de flags; su presencia en esa rama no demuestra
que estuvieran activos en la aplicación que vio el usuario. `main` no contenía
esos flags ni `experiments.py`.

| Cambio | Valor aprovechable | Riesgo concreto |
| --- | --- | --- |
| `subset`: herramientas por palabras clave | Reduce esquemas | Si reconoce un tema y no otro, oculta herramientas necesarias. Vocabulario principalmente español y sin descubrimiento para recuperar las excluidas. |
| `fastpath`: tiros sin modelo | Ahorra inferencias | Construye argumentos con partido/equipo, pero omite jugadores y `context.scope`: puede consultar todo el partido ante una petición de una ventana. |
| `topo`: una consulta, siempre `summary` | Acota operaciones costosas | Bloquea comparaciones o varios instantes/productos topológicos explícitos y modifica la vista solicitada. |
| `delta`: catálogo incremental | Evita repetir evidencia | Recordar sólo IDs pierde modificaciones de contenido o alcance; debe comunicar actualizaciones y retiradas. |
| `state`: estado de tarea | Explica lo disponible y pendiente | Detectar gráficos por palabras españolas no cubre el catálogo ni las peticiones multilingües. |
| `graceful`: cierre parcial | Conserva trabajo ante fallos | No debe afirmar revisión visual exitosa ni sustituir productos o publicar afirmaciones inválidas. |
| `slow` y nuevos límites | Diagnóstico de modelos locales | Aumentar plazos no optimiza latencia. Los límites por defecto de Data crecen de 160.000 a 400.000 tokens observados y de 240 a 600 segundos. |

No se trasladan proveedores NIM/Ollama, flags, selección automática de modelos,
límites ampliados ni restricciones topológicas. Se mantienen las capacidades
autorizadas y los límites vigentes de `main`.

## Revisión y mejoras por agente

| Componente | Capacidades conservadas | Mejora aplicada |
| --- | --- | --- |
| Intérprete | Delegaciones tipadas, catálogo, historial, crear/modificar/aclarar/explicar | Idioma explícito o inferido por el modelo, preferencia previa, recuperación de un único partido seleccionado omitido, validación de equipos cuando hay metadatos, trazabilidad de turnos/tokens. Rechaza lotes de delegaciones cerrando todos los `call_id`. |
| Data | Todas las operaciones autorizadas descubiertas con esquema idéntico, caché, originales, paginación y procedencia | Descripciones locales confiables, pistas de enums del esquema y previews que identifican omisiones. Recupera filtros únicos explícitos omitidos y rechaza partido/equipo ajenos o ensanchamiento de ventana/período; permite subventanas. |
| Analista deportivo | Hechos, placeholders, citas, revisión numérica y distinción de observación/interpretación/recomendación | Catálogo incremental por contenido con retiradas; estado estructurado de evidencia/revisión/presupuesto. Un fallo delegado con hechos disponibles permite una respuesta parcial validada, conserva su código y declara revisión incompleta. Las cifras inválidas requieren reparación, sin eliminar afirmaciones automáticamente. |
| Constructor / Insights HTTP | MCP, 30 recetas, planes declarativos, revisiones y composición sin HTML del modelo | Propaga idioma a Data y al plan, usa descripciones confiables, conserva idioma al adjuntar análisis, publica `lang` correcto y traduce la copia principal del informe. Referencias desplegables en cada idioma. |
| Planner/Resolver/Composer alternativo y A2A | Interpretación separada de resolución determinista, catálogo precargado y disponibilidad por fuente | Idioma explícito en intención/manifiesto; títulos generales, resumen, decisiones principales y errores localizados. Consultas y semántica del resolvedor conservadas. |

Se añaden controles acotados para detectar goles citados como tiros y viceversa
en los seis idiomas, ciertas garantías de impenetrabilidad/victoria y expresiones
de fases tácticas en la protección existente de geometría. **Son controles
léxicos, no una prueba general de que toda conclusión se desprende de sus citas.**

La evidencia no se traduce ni reescribe. IDs, enums, unidades, rutas y operaciones
conservan sus formas originales. La fuente sintética continúa identificada y
xG ausente nunca se convierte en cero.

## Idiomas y uso

Idiomas: español (`es`), inglés (`en`), portugués (`pt`), francés (`fr`), italiano
(`it`) y alemán (`de`). Los dos últimos amplían contextos futbolísticos sin
incorporar modelos ni servicios.

En el chat principal el intérprete devuelve el idioma del mensaje o el solicitado
por el usuario. Recibe la preferencia anterior para seguimientos ambiguos.
También se puede fijar `language` explícitamente en el mensaje: el anfitrión le
da prioridad, lo guarda y lo propaga a Data, Analysis e Insights. La inferencia
automática depende del modelo, sin detector por palabras clave.

Ejemplo de solicitud directa al analista:

```json
{
  "request_text": "Compare both teams' shots in the selected window.",
  "language": "en",
  "context": {
    "match_ids": [900001],
    "scope": {"kind": "window", "period": 2, "start_ms": 10000, "end_ms": 20000}
  }
}
```

Los endpoints directos conservan español por defecto. `language` acepta esos
seis códigos, no locales regionales ni nombres libres. La copia revisada vive
en `src/inside_game/locales/`, incluida en el paquete; no usa un traductor externo.

Los controles globales del frontend, algunas etiquetas internas de recetas,
advertencias originales y metadatos técnicos pueden seguir en español o en el
idioma de su fuente. Esto habilita conversación y análisis multilingües; no
afirma traducir toda la interfaz.

## Contexto y capacidades

El primer catálogo del analista es completo. Las respuestas de herramientas
posteriores sólo envían entradas nuevas o modificadas. Comparar contenido
permite actualizar alcances que reutilizan un ID; `removed_fact_ids` comunica
retiradas. El historial conserva hechos vigentes y el anfitrión todos los
originales para validar el resultado.

No se recortan pares de llamadas/resultados ni se descartan productos para
ahorrar contexto. No se reduce el catálogo según el idioma. Los límites siguen
vigentes: tareas que los superen todavía pueden devolver error o resultado
parcial. No se garantiza tamaño arbitrario ni menos de un minuto de latencia.

## Validación y límites

Resultado final local: **519 pruebas pasan en 17,00 s**, incluidas 66 regresiones
nuevas. Ruff pasa en los archivos Python modificados y `git diff --check` no
reporta errores de espacios. No se atribuyen estas cifras a pruebas del modelo
externo ni a mediciones de producción.

`tests/test_agent_reliability_multilingual.py` cubre contratos, copia fija,
herramientas disponibles, filtros y ventanas del segundo período, reconstrucción
de deltas, metadatos MCP no confiables, recuperación parcial, referencias, HTML
escapado e idioma del documento. Usa modelos programados y MCP/HTTP en memoria.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check <archivos Python modificados>
```

Estas pruebas **no son QA lingüística del modelo real** ni evaluación de las
30 recetas con solicitudes naturales en seis idiomas. No se hicieron
inferencias externas ni consultas nuevas a Azure. Detección de idioma, calidad
deportivo-lingüística, latencia y tareas compuestas requieren evaluación aparte
con el modelo seleccionado. No se declara una mejora porcentual en producción
a partir de estas pruebas programadas.

Se mantienen la protección `INSIDE_GAME_OPENCODE_FREE_ONLY=1`, verificación de
precio cero, identidad deportiva y UUID de sesión. No se habilitan Extra Usage,
recargas, cambios de facturación ni proveedores nuevos. El presupuesto de
seguimiento de Azure **no corta consumo**.

## Fuentes primarias consultadas

- [Building effective agents — Anthropic](https://www.anthropic.com/research/building-effective-agents): patrones simples, responsabilidades claras y herramientas especificadas.
- [Effective context engineering — Anthropic](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents): gestionar contexto y estado sin perder evidencia relevante.
- [Tools — MCP, revisión 2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18/server/tools): descubrimiento, esquemas, resultados y errores. Referencia consultada, no afirmación de última revisión.

Las decisiones son una aplicación al repositorio, no una certificación emitida
por esas fuentes.
