# Calidad y cobertura de los datos sintéticos 3.0.0

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
