"""Publish the close-out report only after cloud and negative checks pass."""
import json
import pathlib

root=pathlib.Path(__file__).parent
read=lambda name:json.loads((root/name).read_text(encoding='utf-8-sig'))
seed=read('seed-report.json');cloud=read('realism-cloud-report.json');structure=read('validation-report.json');negative=read('audit-tests-report.json');before=read('audit-before.json')
assert seed['version']=='2.0.0'
assert cloud['status']=='passed' and len(cloud['reports'])==10
assert structure['status']=='passed' and len(structure['tests'])==31
assert negative['status']=='passed' and len(negative['tests'])==16
assert structure['counts']==seed['counts']
assert all(r['status']=='passed' and not r['errors'] for r in cloud['reports'])
metrics=[r['metrics'] for r in cloud['reports']]
fmt=lambda n:format(n,',').replace(',','.')
doc=f'''# Cierre de calidad: esquema y datos sintéticos 2.0.0

Estado: **APROBADO para desarrollo, demostraciones y consultas analíticas del escenario definido**.
Fecha de la auditoría de Azure: {cloud['testedAt']}.

## Resultado y alcance

Se conservaron las 30 tablas, 43 claves foráneas y los identificadores de los 10 partidos. Se regeneraron sus eventos y tracking, con procedencia y versión sintética explícitas. Los datos de la nube se leyeron de nuevo para la auditoría; este informe no se basa únicamente en la ejecución local del generador.

La carga contiene {fmt(seed['counts']['events'])} eventos, {fmt(seed['counts']['event_passes'])} pases, {fmt(seed['counts']['event_shots'])} tiros, {fmt(seed['counts']['lineup_cards'])} tarjetas y {fmt(seed['counts']['tracking_player_positions'])} posiciones de jugadores. Hay {fmt(seed['counts']['tracking_frames'])} frames y la misma cantidad de posiciones de balón. Los 30 tipos de tabla tienen datos.

## Problemas encontrados en la primera carga

| Problema | Evidencia anterior | Corrección |
|---|---:|---|
| Códigos de tiro Blocked / Off T intercambiados | {before['outcomeCodes'][0]['wrong_shot_outcome_names']} tiros | Catálogo contrastado con datos de origen |
| Tiros Off T terminando dentro de la portería | {before['shotGeometry'][0]['off_target_inside_goal']} | Finales geométricos compatibles con el resultado |
| Asistencia dirigida a otro jugador | {before['assistRecipient'][0]['assist_to_other_player']} | El receptor del pase es el rematador |
| Pase incompleto utilizado como asistencia | {before['assistCompletion'][0]['incomplete_pass_assists']} | Se exige pase completado y recepción anterior al tiro |
| Misma posesión atribuida a distintos equipos | {before['possessions'][0]['possession_conflicts']} grupos | Posesiones secuenciales con equipo estable |
| Presión a más de 10 m del balón | {before['pressures'][0]['distant_pressures']} acciones | Defensor junto al poseedor; control de distancia ≤3 m |
| Todos los partidos terminaban 1–1 | 10 de 10 | Resultados derivados de los goles de cada simulación |
| Balón siempre a altura cero, incluso al final de tiros elevados | Toda la carga | Trayectorias y alturas coherentes con el final del tiro |
| Códigos de posiciones, duelos y tarjetas incoherentes con sus nombres | Detectados al contrastar el catálogo | Identificadores y etiquetas canónicos |

Los resultados idénticos eran una falta de variedad, no una contradicción del marcador con sus goles. La primera validación de FK no era suficiente para certificar coherencia deportiva.

## Comprobaciones ejecutadas

- **31 pruebas de integridad en Azure**, con rechazo de datos inválidos, incluidas las nuevas reglas de asistencias, posesiones, códigos y altura del tiro.
- **16 pruebas negativas del auditor**: se introducen errores deliberados de velocidad, balón, asistencia, marcadores, presión, captura, etiquetas y estado de juego para comprobar que se detectan.
- **Auditoría completa de los 10 partidos leídos de Azure**: sin fallos en los controles ejecutados.
- Consultas de tiros a puerta, xG, posiciones, mapas de calor, duelos, presión y jugadores cercanos ejecutadas contra la nueva carga.
- Todas las FK permanecen habilitadas y confiables; los triggers de integridad quedan habilitados. Las filas de prueba se revierten y no quedan en la base.

La auditoría comprueba cobertura por frame, 11 jugadores por equipo, actor activo, transformación entre coordenadas, coincidencia evento/actor, cercanía de presiones/disputas/faltas, salida y recepción de cada pase, pases completados sin fuera de juego según las posiciones de esa muestra, coherencia de asistencias, resultado y final de tiros, contacto del portero o bloqueador, goles frente al marcador, saques de centro, capturas 360 frente al tracking y continuidad del movimiento entre muestras del mismo período.

En los datos finales, la velocidad máxima entre muestras de jugadores es **{max(m['maxPlayerSpeed'] for m in metrics):.2f} m/s** y la del balón es **{max(m['maxBallSpeed'] for m in metrics):.2f} m/s**. Los jugadores de campo recorren entre **{min(m['minOutfieldDistance'] for m in metrics)/1000:.2f} y {max(m['maxOutfieldDistance'] for m in metrics)/1000:.2f} km** por partido. Estos valores describen el conjunto; no son parámetros calibrados contra una competición real.

## Protección del esquema

`quality-rules.sql` se ejecuta desde la publicación normal del partido. Impide publicar asistencias imposibles, códigos de tiro incompatibles y posesiones contradictorias. Para la versión sintética 2.0.0 también comprueba goles/marcador, cercanía de acciones y cobertura de jugadores y balón. Las comprobaciones físicas detalladas pertenecen al auditor; una FK por sí sola no puede certificar el realismo del fútbol.

La reparación se hizo con respaldo de la carga anterior y transacciones que bloquean durante la sustitución. Se conservaron los identificadores de partido. El acceso de consultas conserva sus permisos de lectura. Los respaldos están en `backups/`, excluidos de Git.

## Límites para darlo por cerrado

El escenario es una serie de amistosos de entrenamiento, con dos tiempos de 45 minutos, sin sustituciones ni tiempo añadido. Los suplentes están inscritos, pero no juegan. No hay una simulación completa de arbitraje, decisiones tácticas, todas las clases de evento o distribuciones estadísticas profesionales.

El tracking tiene una muestra por segundo; no certifica posiciones o velocidades subsegundo. Las capturas 360 son de campo completo y sintéticas. El xG es una fórmula de demostración por distancia/ángulo, identificada como tal; no es el modelo de StatsBomb ni sirve para evaluar jugadores reales.

Con este alcance, el esquema y la carga quedan listos para construir las consultas y las integraciones previstas. Una ampliación a sustituciones, expulsiones, penaltis o prórrogas exige generar y auditar esos escenarios adicionales; el esquema ya dispone de períodos, alineaciones, posiciones y detalles de eventos para representarlos.

## Evidencia reproducible

- `realism-cloud-report.json`: auditoría de lo almacenado en Azure.
- `validation-report.json`: pruebas de restricciones y resultados de consultas.
- `audit-tests-report.json`: detección de errores provocados.
- `seed-report.json`: cantidades y versión.
- `audit-before.json`: evidencia de los problemas originales.

```powershell
npm run validate
npm run audit
npm run audit:tests
```
'''
(root/'DATA-QUALITY.md').write_text(doc,encoding='utf-8')
deployment=read('deployment.json');deployment.update({'syntheticVersion':'2.0.0','qualityStatus':'passed','auditedMatches':10,'integrityTests':31,'auditorNegativeTests':16,'qualityAuditedAt':cloud['testedAt']})
(root/'deployment.json').write_text(json.dumps(deployment,indent=2)+'\n',encoding='utf-8')
print('Quality close-out published: 10 cloud matches, 31 integrity tests, 16 negative audit tests.')
