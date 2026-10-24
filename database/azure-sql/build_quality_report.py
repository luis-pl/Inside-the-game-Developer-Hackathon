"""Build the historical synthetic report without replacing real-data findings."""
import collections
import json
import pathlib

root = pathlib.Path(__file__).parent
read = lambda name: json.loads((root / name).read_text(encoding='utf-8-sig'))
seed, cloud, structure, negative, coverage = map(read, [
    'seed-report.json', 'realism-cloud-report.json', 'validation-report.json',
    'audit-tests-report.json', 'coverage-cloud-report.json'])
assert seed['version'] == '3.0.0'
assert cloud['status'] == 'passed' and len(cloud['reports']) == 10
assert structure['status'] == 'passed' and len(structure['tests']) == 31
assert negative['status'] == 'passed' and len(negative['tests']) == 30
assert coverage['status'] == 'passed' and all(c['passed'] for c in coverage['checks'])
for name, count in seed['counts'].items():
    if name in structure.get('syntheticCounts', {}):
        assert structure['syntheticCounts'][name] == count
    else:
        assert structure['counts'][name] >= count
assert all(r['status'] == 'passed' and not r['errors'] for r in cloud['reports'])
metrics = [r['metrics'] for r in cloud['reports']]
fmt = lambda n: format(n, ',').replace(',', '.')
counts = collections.Counter()
names = {}
for row in coverage['sections']['types']:
    counts[row['type_id']] += row['n']
    names[row['type_id']] = row['type_name']
table = '\n'.join(f'| {id} | {names[id]} | {fmt(n)} |' for id, n in sorted(counts.items()))
air = coverage['sections']['aerial'][0]
restarts = ', '.join(f"{r['restart']}: {r['n']}" for r in coverage['sections']['restarts'])
doc = f'''# Calidad y cobertura de los datos sintéticos 3.0.0

Estado: **validación superada para las operaciones y escenarios documentados de la hackathon**.
Lectura completa desde Azure: {cloud['testedAt']}. Cobertura: {coverage['testedAt']}.

## Corrección de la cobertura

La versión 2.0.0 superaba los controles anteriores, pero omitía acciones básicas necesarias para la analítica. Ese cierre era insuficiente. Ahora se conservan las 30 tablas, 43 FK y los diez identificadores de partido, exigiendo cobertura y coherencia.

La carga contiene {fmt(seed['counts']['events'])} eventos, {fmt(seed['counts']['event_passes'])} pases y {fmt(seed['counts']['event_shots'])} tiros; {fmt(seed['counts']['tracking_frames'])} frames, {fmt(seed['counts']['tracking_player_positions'])} posiciones activas y {fmt(seed['counts']['tracking_ball_positions'])} posiciones de balón. Los 56 inscritos participan en intervalos efectivos. Hay respaldos completos anteriores a cada reemplazo en la carpeta local backups/, excluida de Git.

| ID | Acción | Filas en diez partidos |
|---|---|---:|
{table}

Las familias analíticas exigidas existen **en cada partido**, no sólo en un catálogo de tipos. Hay regates completos e incompletos, quites ganados y perdidos, conducciones, intercepciones, recepciones, malos controles, desposesiones, bloqueos y despejes.

Hay **{air['linked_contests']} disputas aéreas** con dos perspectivas enlazadas: perdedor Duel/type=Aerial Lost y ganador Clearance/aerial_won=true, con cuerpo Head. No se inventa un código Aerial Won. Contar las dos perspectivas como dos disputas duplicaría el total.

Una recepción correcta seguida de mal control o regate fallido no convierte retroactivamente el pase recibido en incompleto. Las recepciones se enlazan con sus pases completados.

Reanudaciones en pases: {restarts}. Se registran tiros de cabeza y ambas piernas, así como pases Ground, Low y High. cross, switch y cut_back se basan en reglas geométricas explícitas de la simulación; through_ball y technique permanecen sin anotación. NULL no equivale a false.

## Sustituciones y presencia

Hay 60 sustituciones: tres por equipo y partido, durante detenciones del balón. El evento identifica saliente y entrante; desde el segundo siguiente, tracking y capturas usan al reemplazo y el saliente deja de aparecer. lineup_positions registra los intervalos; Tactical Shift actualiza los participantes manteniendo 433.

Cada frame conserva 11 activos por equipo. Se comprueban los intervalos contra cada muestra y contra los minutos efectivamente cubiertos. Los extremos de los períodos no agregan segundos ficticios. No se asignan coordenadas cero a jugadores fuera de cancha.

El cambio de identidad se simula en el puesto de juego; no se modela la caminata desde/hacia el banco. La posición existe para cada jugador **activo en cada segundo muestreado**. Un instante intermedio requiere interpolación identificada.

## Validaciones ejecutadas

- **31 pruebas de restricciones y publicación en Azure**.
- **30 pruebas negativas del auditor**: errores de balón, velocidad, asistencias, códigos, posesión, regates, conducciones, duelos aéreos, atribución de quites, recepción, sustituciones y ausencia de familias.
- **{len(coverage['checks'])} controles adicionales de cobertura en Azure**, con nueve consultas analíticas nuevas y siete consultas originales ejecutadas.
- **Auditoría completa de los diez partidos leídos desde Azure**, sin errores en los controles ejecutados.
- FK habilitadas y confiables, triggers habilitados y ninguna fila de prueba persistente.

Se comprueban actores activos, intervalos, contactos con el balón, rivales cercanos cuando corresponde, pases/recepciones/asistencias, goles/marcadores, geometría y contacto de tiros, altura de duelos aéreos y correspondencia entre capturas y tracking. Las conducciones mantienen control del balón y no se superponen con regates anotados.

Máximos entre muestras: jugadores **{max(m['maxPlayerSpeed'] for m in metrics):.2f} m/s**, aceleración **{max(m['maxPlayerAcceleration'] for m in metrics):.2f} m/s²**, balón **{max(m['maxBallSpeed'] for m in metrics):.2f} m/s**. Las distancias individuales se comparan junto con los minutos efectivos: los suplentes no juegan 90 minutos.

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
'''
(root / 'DATA-QUALITY-SYNTHETIC.md').write_text(doc, encoding='utf-8')
deployment = read('deployment.json')
deployment.update({'syntheticVersion': '3.0.0', 'qualityStatus': 'passed-coverage-and-coherence',
                   'auditedMatches': 10, 'integrityTests': 31, 'auditorNegativeTests': 30,
                   'coverageChecks': len(coverage['checks']), 'qualityAuditedAt': cloud['testedAt']})
(root / 'deployment.json').write_text(json.dumps(deployment, indent=2) + '\n', encoding='utf-8')
print(f"Quality evidence published: ten Azure matches, 31 SQL tests, 30 negative tests, {len(coverage['checks'])} coverage checks.")
