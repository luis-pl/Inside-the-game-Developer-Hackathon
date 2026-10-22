# Cierre de calidad: esquema y datos sintéticos 2.0.0

Estado: **APROBADO para desarrollo, demostraciones y consultas analíticas del escenario definido**.
Fecha de la auditoría de Azure: 2026-10-22T02:12:07.062Z.

## Resultado y alcance

Se conservaron las 30 tablas, 43 claves foráneas y los identificadores de los 10 partidos. Se regeneraron sus eventos y tracking, con procedencia y versión sintética explícitas. Los datos de la nube se leyeron de nuevo para la auditoría; este informe no se basa únicamente en la ejecución local del generador.

La carga contiene 10.815 eventos, 5.797 pases, 225 tiros, 24 tarjetas y 1.188.440 posiciones de jugadores. Hay 54.020 frames y la misma cantidad de posiciones de balón. Los 30 tipos de tabla tienen datos.

## Problemas encontrados en la primera carga

| Problema | Evidencia anterior | Corrección |
|---|---:|---|
| Códigos de tiro Blocked / Off T intercambiados | 160 tiros | Catálogo contrastado con datos de origen |
| Tiros Off T terminando dentro de la portería | 80 | Finales geométricos compatibles con el resultado |
| Asistencia dirigida a otro jugador | 240 | El receptor del pase es el rematador |
| Pase incompleto utilizado como asistencia | 40 | Se exige pase completado y recepción anterior al tiro |
| Misma posesión atribuida a distintos equipos | 1190 grupos | Posesiones secuenciales con equipo estable |
| Presión a más de 10 m del balón | 1029 acciones | Defensor junto al poseedor; control de distancia ≤3 m |
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

En los datos finales, la velocidad máxima entre muestras de jugadores es **5.45 m/s** y la del balón es **23.14 m/s**. Los jugadores de campo recorren entre **7.32 y 7.68 km** por partido. Estos valores describen el conjunto; no son parámetros calibrados contra una competición real.

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
