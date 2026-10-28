# Datos sintéticos y procedencia de los campos

La demo dispone de **diez partidos completamente sintéticos**, `900001`–`900010`.
Sus equipos usan nombres ficticios, sus eventos y trayectorias fueron generados y
su xG procede de `toy-distance-angle-v2`: es ilustrativo, no está calibrado para
predecir fútbol profesional. Esta es la selección adecuada para mostrar una
experiencia construida sobre datos sintéticos.

El catálogo de investigación conserva por separado dos partidos Metrica
(`900011`, `900012`) y ocho SkillCorner (`900101`–`900108`). Esas importaciones
conservan eventos y posiciones de sus fuentes con identidades enmascaradas.
La ausencia de nombres personales no cambia la procedencia de esas mediciones.
Los alias tampoco permiten afirmar anonimización irreversible.

| Dato o transformación | Partidos sintéticos | Catálogo de referencia |
|---|---|---|
| Equipos y jugadores | Identidades ficticias generadas | Identidades sustituidas por alias; no son nombres personales originales |
| Eventos y trayectorias | Simulados por el generador | Observaciones o eventos derivados del proveedor, normalizados para el esquema |
| xG | Generado por un modelo ilustrativo | Ausente (`null`) en ambas importaciones actuales |
| Posiciones ausentes | Según configuración y cobertura del generador | Se conservan como ausentes; no se inventan recorridos para rellenarlas |
| Extrapolaciones SkillCorner | No corresponde a esta fuente | Se distinguen de las observaciones mediante `sample_method=extrapolated` |
| Interpolación visual | Dibujo entre muestras | Dibujo entre muestras; no se incorpora como observación ni alimenta métricas |
| Voronoi, forma, homología y Hodge | Cálculos derivados de la simulación | Cálculos derivados de los datos de referencia; no son nuevas observaciones |
| Posesiones y balón en juego de Metrica | No corresponde a esta fuente | Inferencias identificadas, no anotaciones originales confirmadas |

## Qué sería un enriquecimiento sintético

Si se añaden goles esperados, eventos, posiciones u otros atributos generados a un
partido observado, la descripción sería **fuente seudonimizada con enriquecimiento
sintético**. Hay que identificar qué campos se generan, su método/versión, alcance
y limitaciones. No se cambia `is_synthetic` de toda la fuente para ocultar el
origen de los campos que siguen siendo observados. Un derivado geométrico tampoco
equivale a una medición independiente de control, presión o calidad defensiva.

## Verificación del 27 de octubre de 2026

Una consulta de lectura `get_shots(view="summary")` sobre la API desplegada confirmó:

| Partido de muestra | Procedencia devuelta | xG |
|---|---|---:|
| `900001` | `is_synthetic=true`, `data_kinds=["synthetic"]` | 1.6903801272059698 |
| `900011` | `is_synthetic=false`, `data_kinds=["real_anonymized"]` | `null` |
| `900101` | `is_synthetic=false`, `data_kinds=["real_pseudonymized"]` | `null` |

Esta comprobación cubre una muestra de cada conjunto; los informes de preparación
y carga describen la cobertura completa. No se añadieron atributos, modificaron
filas ni sustituyeron metadatos durante esta revisión.

Fuentes de implementación: `scripts/prepare_metrica.py`,
`scripts/prepare_skillcorner.py`, `database/azure-sql/synthetic.mjs` y
[DATA-QUALITY.md](../database/azure-sql/DATA-QUALITY.md). El visor selecciona
actualmente las fuentes de referencia por defecto; esta aclaración documental
no cambia esa selección. El chat permite elegir los partidos sintéticos.
