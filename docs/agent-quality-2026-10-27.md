# Pruebas de agentes, evidencia y contexto — 27 de octubre de 2026

Se probaron los cuatro agentes con Beam Free en OpenCode Go, MCP y la API de
datos real. La tanda final pasó **8 de 8 escenarios**, seguida de un canario
adicional con el código final. Pasan **546 pruebas locales en 18,09 s**; Ruff y
`git diff --check` pasan. Este informe amplía la revisión inicial de
[ramas y multilingüismo](agent-reliability-multilingual.md).

Los resultados resumidos y la telemetría acotada están en
[agent-quality-verification.json](agent-quality-verification.json). Los prompts
exactos y sus verificadores viven en `scripts/qa_agents_quality.py`. Los artefactos
completos de diagnóstico se conservan localmente en `.temp/agent-quality/`,
incluidos intentos fallidos; esa carpeta está excluida de Git.

## Escenarios con el modelo real

| Caso | Resultado comprobado | Tiempo de la tanda final |
| --- | --- | ---: |
| Secuencia de pases ES | `pass_map`, `structural_pass` y `play_replay`; rivales incluidos, orientación del contexto y secuencia pasador–receptor citada | 70,238 s |
| Reconstrucción ES | Mapa y replay de la misma ventana | 50,152 s |
| Reconstrucción EN | Mapa y replay de la misma ventana, análisis en inglés | 44,145 s |
| Tiros y xG sintéticos ES | Exactamente un mapa combinado y una evolución de xG; procedencia sintética explícita | 54,099 s |
| xG no disponible PT | Explica el límite y ofrece alternativa; no fabrica xG ni publica gráfico vacío | 10,036 s |
| Dos instantes FR | Dos `team_shape`, observaciones a 600.000 y 601.000 ms; no una tendencia del partido | 56,093 s |
| Jugada ambigua IT | Solicita aclaración sin inventar partido ni informe | 6,031 s |
| Red de pases DE | Un gráfico, segundo período, ventana de 10–20 s y equipo seleccionado | 62,106 s |

La tanda usó 83 llamadas de inferencia. Después de los últimos ajustes se repitió
el caso compuesto de tres bloques: **52,185 s y 9 llamadas**, con todos los
controles aprobados. Son observaciones de ejecuciones concretas, no un SLA ni
una estimación estadística de fiabilidad o latencia.

Las reconstrucciones usaron Metrica, partido 900011, equipo 103, primer período,
ventana `[0, 20000)`. Se verificaron **100 observaciones a 5 Hz**, sin interpolar
ausencias, y los seis enlaces pasador–receptor contra eventos y nombres de la
fuente. Cada cifra citada se resolvió contra el JSON original o contra una
métrica del renderizador con evidencia asociada. Este control comprueba valores
y referencias; no demuestra automáticamente toda interpretación táctica.

En navegador se comprobó avanzar a la observación 50 (10,0 s, 22 jugadores),
reproducir, detener al final en la observación 99 (19,8 s), y filtrar el bloque.
La captura local está en `.temp/agent-quality/replay-verified.png`.

También pasaron **6 de 6 pruebas reales de detección automática de idioma**:
español, inglés, portugués, francés, italiano y alemán, sin fijar `language` en
esas llamadas. La tanda de ocho casos sí fija el idioma para comprobar su
propagación. Los nombres, IDs y evidencia original mantienen su idioma fuente;
esto no acredita traducción completa de todos los controles de interfaz.

## Disponibilidad del catálogo

Se ejecutó una matriz determinista de **30 recetas × 3 fuentes** contra la API,
sin LLM y sin sobrescribir los perfiles de disponibilidad.

| Partido / fuente | Disponibles | Parciales | No disponibles |
| --- | ---: | ---: | ---: |
| 900001 / sintética | 29 | 1 | 0 |
| 900011 / Metrica anonimizada | 24 | 0 | 6 |
| 900101 / SkillCorner | 26 | 1 | 3 |

La matriz mide disponibilidad técnica de esas tres muestras. Se capturó antes
del último ajuste de ocultación de campos no anotados y no certifica su copia
editorial final. El ajuste posterior tiene regresiones locales y verificación
de los informes Metrica finales. No es QA natural de las 30 recetas en seis
idiomas, ni QA de todos los partidos del corpus.

## Fallos encontrados y correcciones

| Problema observado | Corrección y evidencia |
| --- | --- |
| El modelo copiaba filtros y ventanas con formas inválidas; gastaba turnos reparándolos | Esquemas de Data proyectan filtros ya fijados, heredados y validados por el anfitrión. Descubrimiento restaura el esquema completo para refinamientos. Errores incluyen rutas y tipos concretos. |
| Solicitud a 5 Hz acababa en 1 Hz | `sample_step_ms` atraviesa contratos y delegaciones; el anfitrión exige 200 ms y stride 1 cuando se solicita. Sólo el enum finito del intérprete admite normalización auditada de cadenas numéricas. |
| Una instantánea heredaba además una ventana incompatible | Período heredado; instante validado dentro de la ventana, sin añadir un segundo selector temporal. La comparación francesa final pasó. |
| El equipo focal recortaba el tracking de rivales | El foco de análisis se separa de la población de tracking; se preservan ambos equipos para geometría relacional. |
| Dos gráficos pedidos se convertían en cuatro | `required_insights` conserva el multiconjunto solicitado; Insights rechaza cantidades o recetas distintas antes de renderizar. La repetición de una receta sigue permitida cuando se solicitan dos instantes. |
| Ceros de campos no anotados parecían hechos | Política por procedencia, incluida la forma anidada `provenance.datasets`: excluye esos campos de hechos citables y métricas visibles sin modificar originales. En Metrica no se afirman centros/cutbacks/cambios de orientación, intentos o tasa de éxito ausentes. |
| Reconstrucción sólo daba agregados | Hechos `recorded_pass_link` para episodios cortos completos, con instante y nombres canónicos; no muestrea silenciosamente secuencias largas. No infiere vuelo del balón, intención, control o presión. |
| Nombres anonimizados con números provocaban reparaciones numéricas | Nombres exactos conocidos se transforman en referencias a hechos. Un nombre puramente numérico o una cifra arbitraria no se normaliza. La frecuencia se deriva del espaciado observado, no del prompt. |
| Timeout exterior descartaba evidencia antes del cierre parcial | Data calcula el plazo restante después de abrir MCP y deja margen para devolver resultados parciales. |
| Fallaba la prosa después de publicar gráficos | Se conserva el informe publicado y se devuelve análisis parcial con su código de fallo. Prueba HTTP de fallo al adjuntar y de vencimiento después del gráfico. |

Hubo fallos reales durante el diagnóstico: argumentos mal serializados,
muestreo incorrecto, duplicación de gráficos y agotamiento de plazos. También se
corrigió el sondeo del propio harness, que inicialmente alcanzaba el límite de
peticiones. Los directorios `baseline-fixed-poll`, `interpreter-repair`,
`corpus-initial`, `final` y `verified-final` conservan esos intentos. `verified-final`
fue interrumpido al detectar la procedencia anidada mal interpretada; la tanda
completa posterior aprobada es **`verified-current`**. No se presenta el total
histórico de intentos como un 100 % de aciertos.

## Contexto, compactación y optimización

Data entrega un manifiesto completo de capacidades autorizadas y carga de forma
progresiva los esquemas necesarios. `describe_data_tools` permite recuperar
cualquier operación del catálogo y su esquema completo; la selección inicial
usa identificadores de operación, sin diccionario de temas por idioma.
`tool_schema_mode="full"` conserva la opción diagnóstica del catálogo completo.
No se restringen recetas topológicas ni se cambian proveedores o presupuestos.

En el caso compuesto medido, los esquemas de Data pasaron de **68.955 a 6.534
bytes por llamada**: aproximadamente 90,5 % menos de serialización de esquemas.
En los ocho casos finales oscilaron entre 3.844 y 8.963 bytes. Esto no significa
90,5 % menos de tokens totales ni una reducción garantizada de latencia. El
manifiesto de herramientas sigue presente. El catálogo de hechos del analista
envía deltas por contenido y retiradas; un checkpoint vuelve a hidratarlo completo.

El proveedor publicó `limit.context=1048576` tokens. Antes de conocerlo se
registra `null`. En la tanda final el mayor input observado fue 25.316 tokens;
los 83 eventos quedaron por debajo del umbral. En el canario final fueron
22.785 tokens como máximo. **No hizo falta compactar esas ejecuciones reales.**

La política implementada es:

1. Medir el input serializado incluyendo herramientas y mensajes efectivos;
   distinguir bytes de aplicación y tokens observados del proveedor, incluidos
   tokens de entrada cacheados cuando son reportados.
2. Activar checkpoint al 75 % del presupuesto de aplicación, o al 75 % de la
   ventana nativa estimada reservando salida. La relación tokens/bytes es una
   estimación basada en uso observado, no un tokenizador exacto.
3. Compactar sólo con todas las llamadas de herramientas cerradas. Mantener
   UUID, solicitud original, idioma, filtros, datos completos vigentes, consultas,
   cobertura, advertencias, procedencia y capacidades habilitadas. El historial
   de errores conserva los tres errores sanitizados recientes.
4. Sustituir únicamente si el checkpoint es menor. No se usa un LLM resumidor,
   no se conservan razonamientos privados en el checkpoint ni se cortan hechos.
   Si todavía excede el límite de bytes o el límite nativo estimado, detener con
   `CONTEXT_BUDGET_EXCEEDED`.

Se probaron bajo presión artificial la identidad exacta del estado recuperado,
errores, herramientas, referencias pendientes, checkpoint demasiado grande,
rehidratación del analista y rechazo de desbordamiento nativo estimado. Esas
pruebas son locales y deterministas; no simulan una certificación de uso de
un millón de tokens con el proveedor. El intérprete conserva el historial
original: si éste por sí solo excede su presupuesto, falla de forma explícita.

## Reproducción y presupuesto

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/qa_agents_quality.py --live --preflight
.\.venv\Scripts\python.exe scripts/qa_agents_quality.py --live --language-probes --output-dir .temp/agent-quality/languages-new
.\.venv\Scripts\python.exe scripts/qa_agents_quality.py --live --output-dir .temp/agent-quality/batch-new
.\.venv\Scripts\python.exe scripts/qa_agents_quality.py --verify-existing --output-dir .temp/agent-quality/verified-current
.\.venv\Scripts\python.exe scripts/insights_availability.py --match-id 900001 --match-id 900011 --match-id 900101 --output-dir .temp/agent-quality/availability-new
```

Las opciones `--live` y la configuración preexistente son necesarias para inferir.
El harness exige Go, `beam-free`, `cli_session` y `free_only`; no selecciona otro
modelo. El proveedor comprueba precios cero antes de cada inferencia. La
telemetría de las tandas comparadas reportó `cost=0`; esto no es una auditoría de
facturación de Azure. Las consultas reales usan la API ya autorizada. No se
habilitaron recargas, Console, Extra Usage ni servicios nuevos. El presupuesto
de seguimiento de Azure no corta consumo.

Los cambios quedan en el árbol local: no se hizo push ni despliegue. La revisión
de prácticas y sus fuentes primarias están enlazadas en el informe inicial;
las decisiones aquí descritas son controles comprobados del repositorio, no una
certificación externa de calidad absoluta.
