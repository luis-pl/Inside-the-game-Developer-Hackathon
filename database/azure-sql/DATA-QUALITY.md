# Calidad y procedencia de los datos

## Clasificación para la demo

El catálogo contiene dos conjuntos separados: diez partidos **sintéticos**
(`900001`–`900010`) y diez partidos de referencia con identidades enmascaradas.
Para una demostración basada en datos sintéticos se selecciona el primer conjunto.
Cambiar nombres, normalizar coordenadas o calcular métricas derivadas no convierte
las observaciones de referencia en una simulación. Si se generan atributos sobre
una fuente observada, se documentan por campo como enriquecimiento sintético,
conservando la procedencia de la base. Véase [clasificación por campo](../../docs/data-provenance.md).

## Catálogo de referencia: diez partidos de fuentes distintas

El conjunto actual incorpora **2 partidos de Metrica y 8 de SkillCorner**. Los
diez partidos sintéticos históricos no cuentan para este mínimo. Los ocho nuevos
partidos conservan fuentes distintas; no se duplican registros cambiando alias.

### Nombres de equipos

Los equipos usan alias ficticios con temática de programación (p. ej. «Tabs
United — Spaces Athletic», «Null Pointers — Undefined Athletic»). Son seudónimos:
no identifican a los clubes originales ni corresponden a clubes conocidos. Los
cuatro equipos sintéticos llevan nombres de testing (Mock Objects FC, Test
Fixtures United, Stub City, Dummy Data Rovers) y conservan `is_synthetic` y la
competición «Synthetic Demo League». La correspondencia y los nombres anteriores
(`Synthetic FC n`, `Metrica n · Equipo A/B`, `SC nn · Equipo A/B`) están en
`team-names.json`; `rename-teams.mjs` (o `rename-teams.sql`) los aplica en una
transacción y `--rollback` (o `rename-teams-rollback.sql`) los restaura.
Hay 291.770 frames a 5 Hz y 6.418.940 filas de posición de jugadores, incluidas
las ausencias explícitas. `real-data-cloud-report.json` compara las filas completas
de los diez partidos contra la preparación de las fuentes fijadas por SHA-256.

SkillCorner se publica con licencia MIT y atribución; su tracking proviene de
retransmisiones. Se mantienen separados `observed`, `extrapolated` y `missing`.
Los períodos de repetición o cámara sin campo pueden no contener tracking; no
se rellenan con movimientos creados localmente. El proveedor también advierte
errores de identidad. Los nombres/IDs de jugadores y equipos se enmascaran por
partido y no se importan cumpleaños, nombres ni apellidos. La trazabilidad pública
al partido se conserva; esto es seudonimización, no anonimización irreversible.

Las dimensiones originales (104–106 × 68 m) se normalizan a 105 × 68 m. Los
eventos dinámicos y pases conservan su procedencia. No hay xG ni resultados
individuales de los tiros en la importación de SkillCorner: se devuelven como
desconocidos; el marcador final sí procede del proveedor. No se infiere el gol
de un jugador desde una cadena `lead_to_goal`. Los extremos desconocidos de
pases fallidos no se convierten en coordenadas ficticias ni distancias cero.

Evidencia de SkillCorner: `skillcorner-source.json`, `skillcorner-quality-report.json`,
`skillcorner-load-report.json`, `SKILLCORNER-LICENSE.txt` y auditoría conjunta.

## Componente Metrica: dos partidos reales anonimizados

Los partidos `900011` y `900012` conservan trayectorias y eventos sincronizados
de [Metrica Sports](https://github.com/metrica-sports/sample-data), revisión
`e706dd506b360d69d9d123d5b8026e7294b13996`. No son simulaciones ni se ha aplicado
una formación artificial. `is_synthetic=false`, `data_kind=real_anonymized` y
`sample_method=observed` los distinguen de la demo anterior.

Se mantienen cinco observaciones originales por segundo, seleccionadas de la
fuente a 25 Hz. Cinco minutos contienen 1.500 frames en 300.000 ms. El visor
reproduce un segundo de partido por segundo a 1×; se comprobó además con una
medición de pantalla de 78,6 segundos, con relación temporal aproximada 1,00015.
La interpolación entre observaciones sólo dibuja la animación y no alimenta métricas.

La auditoría `metrica-cloud-report.json` relee **todas** las posiciones, balón,
frames y pases de Azure y compara sus huellas con los archivos normalizados.
Comprueba además 22 identidades activas por frame, 1.500 muestras por ventana
de cinco minutos, alineación evento/tracking hasta 160 ms y ausencia de xG inventado.
Las huellas numéricas normalizan a seis decimales; no son un hash binario del SQL.

La fuente real tiene errores y ausencias: se conservan 219 muestras de jugadores
como ausentes y 22.949 de balón como ausentes. Estas últimas incluyen las
ausencias originales y los puntos descartados. Se descartan saltos entre muestras
superiores a 13 m/s para jugadores o 55 m/s para balón, y coordenadas fuera de un
margen de 5 m respecto al campo. Son umbrales de descarte de errores, **no máximos
profesionales calibrados**. No se estiran recorridos ni se rellenan huecos. Las
posiciones válidas ligeramente fuera de las líneas se conservan para saques y
salidas del campo. Los cambios de identidad se infieren de presencia; un solapamiento
de una muestra se resuelve dando el puesto al entrante.

No hay anotaciones de formación táctica, altura de pase, presión, altura del balón
ni xG; no se infieren a partir de la mera apariencia de una jugada. La bandera
`ball_in_play` y las posesiones son inferencias identificadas, no verdad del proveedor.
Los eventos ambiguos se conservan con su tipo Metrica. Las consultas que necesitan
roles tácticos o altura del pase deben indicar esa limitación; una ausencia de
anotación no demuestra que la acción no ocurrió. La geometría del visor utiliza
las posiciones reales y excluye observaciones ausentes.

Las fechas y competición se mantienen desconocidas; los marcadores SQL de 1900
no son la fecha real del partido. Las capturas 360 y el modelo toy-xG de la demo
anterior no se trasladan a estos partidos.

Evidencia: `metrica-source.json`, `metrica-quality-report.json`,
`metrica-load-report.json`, `metrica-cloud-report.json` y
`../../docs/metrica-service-verification.json`.

## Historial separado: datos sintéticos 3.0.0

La aprobación siguiente sólo cubría los controles de esa simulación. No acreditaba
realismo futbolístico: omitía el ritmo, el movimiento colectivo y la frecuencia
de pausas. La revisión nueva confirmó 80–85 minutos de balón activo por partido,
una señal de que esa simulación no era una base adecuada para la reproducción.

Estado: **validación superada para las operaciones y escenarios documentados de la hackathon**.
Lectura completa desde Azure: 2026-10-23T01:21:13.917Z. Cobertura: 2026-10-23T01:21:13.636Z.

## Corrección de la cobertura

La versión 2.0.0 superaba los controles anteriores, pero omitía acciones básicas necesarias para la analítica. Ese cierre era insuficiente. Ahora se conservan las 30 tablas, 43 FK y los diez identificadores de partido, exigiendo cobertura y coherencia.

La carga contiene 25.012 eventos, 5.752 pases y 209 tiros; 54.020 frames, 1.188.440 posiciones activas y 54.020 posiciones de balón. Los 56 inscritos participan en intervalos efectivos. Hay respaldos completos anteriores a cada reemplazo en la carpeta local backups/, excluida de Git.

| ID | Acción | Filas en diez partidos |
|---|---|---:|
| 2 | Ball Recovery | 639 |
| 3 | Dispossessed | 119 |
| 4 | Duel | 471 |
| 6 | Block | 68 |
| 9 | Clearance | 125 |
| 10 | Interception | 104 |
| 14 | Dribble | 852 |
| 16 | Shot | 209 |
| 17 | Pressure | 2.504 |
| 18 | Half Start | 20 |
| 19 | Substitution | 60 |
| 21 | Foul Won | 195 |
| 22 | Foul Committed | 195 |
| 23 | Goal Keeper | 72 |
| 30 | Pass | 5.752 |
| 33 | 50/50 | 204 |
| 34 | Half End | 20 |
| 35 | Starting XI | 40 |
| 36 | Tactical Shift | 60 |
| 38 | Miscontrol | 103 |
| 39 | Dribbled Past | 733 |
| 42 | Ball Receipt* | 5.421 |
| 43 | Carry | 7.046 |

Las familias analíticas exigidas existen **en cada partido**, no sólo en un catálogo de tipos. Hay regates completos e incompletos, quites ganados y perdidos, conducciones, intercepciones, recepciones, malos controles, desposesiones, bloqueos y despejes.

Hay **125 disputas aéreas** con dos perspectivas enlazadas: perdedor Duel/type=Aerial Lost y ganador Clearance/aerial_won=true, con cuerpo Head. No se inventa un código Aerial Won. Contar las dos perspectivas como dos disputas duplicaría el total.

Una recepción correcta seguida de mal control o regate fallido no convierte retroactivamente el pase recibido en incompleto. Las recepciones se enlazan con sus pases completados.

Reanudaciones en pases: Corner: 17, Free Kick: 195, Goal Kick: 52, Kick Off: 36, Throw-in: 32. Se registran tiros de cabeza y ambas piernas, así como pases Ground, Low y High. cross, switch y cut_back se basan en reglas geométricas explícitas de la simulación; through_ball y technique permanecen sin anotación. NULL no equivale a false.

## Sustituciones y presencia

Hay 60 sustituciones: tres por equipo y partido, durante detenciones del balón. El evento identifica saliente y entrante; desde el segundo siguiente, tracking y capturas usan al reemplazo y el saliente deja de aparecer. lineup_positions registra los intervalos; Tactical Shift actualiza los participantes manteniendo 433.

Cada frame conserva 11 activos por equipo. Se comprueban los intervalos contra cada muestra y contra los minutos efectivamente cubiertos. Los extremos de los períodos no agregan segundos ficticios. No se asignan coordenadas cero a jugadores fuera de cancha.

El cambio de identidad se simula en el puesto de juego; no se modela la caminata desde/hacia el banco. La posición existe para cada jugador **activo en cada segundo muestreado**. Un instante intermedio requiere interpolación identificada.

## Validaciones ejecutadas

- **31 pruebas de restricciones y publicación en Azure**.
- **30 pruebas negativas del auditor**: errores de balón, velocidad, asistencias, códigos, posesión, regates, conducciones, duelos aéreos, atribución de quites, recepción, sustituciones y ausencia de familias.
- **43 controles adicionales de cobertura en Azure**, con nueve consultas analíticas nuevas y siete consultas originales ejecutadas.
- **Auditoría completa de los diez partidos leídos desde Azure**, sin errores en los controles ejecutados.
- FK habilitadas y confiables, triggers habilitados y ninguna fila de prueba persistente.

Se comprueban actores activos, intervalos, contactos con el balón, rivales cercanos cuando corresponde, pases/recepciones/asistencias, goles/marcadores, geometría y contacto de tiros, altura de duelos aéreos y correspondencia entre capturas y tracking. Las conducciones mantienen control del balón y no se superponen con regates anotados.

Máximos entre muestras: jugadores **8.02 m/s**, aceleración **5.70 m/s²**, balón **22.58 m/s**. Las distancias individuales se comparan junto con los minutos efectivos: los suplentes no juegan 90 minutos.

quality-rules.sql conserva los controles de 2.0.0 y añade cobertura mínima, cantidad de sustituciones y actor activo para 3.0.0. El generador ejecuta la auditoría antes de insertar y publica dentro de una transacción; la auditoría independiente vuelve a leer las filas reales de la nube.

## Límites explícitos

Es una simulación de entrenamiento preparada para demostrar análisis; no tiene distribuciones calibradas contra fútbol profesional ni constituye una simulación completa de arbitraje y leyes de juego. La primera oportunidad de tiro de cada partido se prepara como bloqueo para garantizar ese caso de demostración. La formación declarada es siempre 433; los cambios reflejan participantes y no sistemas tácticos distintos.

No hay casos anotados de expulsión, segunda amarilla, penalti, tiro libre directo, fuera de juego, lesión o prórroga. El esquema puede representarlos, pero esta carga no demuestra esos escenarios. El catálogo debe mostrar estas ausencias, en vez de prometer todas las variantes del fútbol.

El tracking es sintético a 1 Hz, las capturas 360 son coordenadas de campo completo y el xG es toy-distance-angle-v2, una fórmula ilustrativa por distancia/ángulo. No son datos reales, fotografías ni el modelo de StatsBomb. La posesión exacta por frame no se almacena: su duración exige inferencia explícita. xT, OBV, EPV, pitch control e impenetrabilidad requieren un modelo o una definición, aunque hay entradas espaciales para construirlos.

## Evidencia reproducible

- seed-report.json: versión y cantidades.
- realism-cloud-report.json: coherencia de filas recuperadas de Azure.
- coverage-cloud-report.json: cobertura y ejemplos analíticos ejecutados.
- audit-tests-report.json: errores provocados detectados.
- validation-report.json: restricciones SQL y consultas originales.
- queries-coverage.sql: intercepciones, regates, conducciones, quites, aéreas, sustituciones, minutos y reanudaciones.
- ../../docs/data-operations-catalog.md: operaciones para diseñar agente, API y MCP; no implementaciones desplegadas.

Comandos: npm run validate, npm run audit, npm run audit:coverage, npm run audit:local y npm run audit:tests.
