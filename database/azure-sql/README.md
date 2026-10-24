# Base de fútbol en Azure SQL

## Datos actuales: partidos reales anonimizados

El visor usa por defecto **diez partidos reales distintos**, sin contar el historial sintético:

| Fuente | Partidos e IDs | Muestreo conservado |
|---|---|---|
| Metrica Sports | 2: `900011`, `900012` | 5 Hz de una fuente a 25 Hz |
| SkillCorner | 8: `900101`–`900108` | 5 Hz de una fuente a 10 Hz |

Son **291.770 frames y 6.418.940 filas de posición de jugadores**, incluidas las
ausencias explícitas. Cada partido corresponde a un partido fuente diferente;
no se repiten recorridos con nombres distintos para completar el catálogo.

Cinco minutos equivalen a **300.000 ms y 1.500 observaciones**, reproducidos en
300 segundos a 1×. Ventanas del visor de más de cinco minutos seleccionan 1 Hz
para limitar transferencia y cálculo; las coordenadas siguen siendo observadas.
Se conservan el tiempo añadido, las identidades durante sustituciones y los
huecos de seguimiento. No se impone una formación 433.

Metrica no aporta xG, formación, altura del balón, presión ni altura de pase.
No se fabrican esos campos. Las fechas y competición originales son desconocidas;
`1900-01-01` y la temporada `1900` son marcadores de importación, señalados en
metadatos. Los pases `PASS` son los completados que identifica la fuente; otros
`BALL LOST` conservan su tipo original y no equivalen automáticamente a pases
fallidos. Por ello en Metrica no se presenta una tasa total de acierto como si fuera conocida.

SkillCorner aporta tracking de retransmisión y eventos dinámicos derivados.
Sus muestras se identifican como observadas o extrapoladas por el proveedor y
conservan los huecos. Sus 6.044 pases incluyen éxitos y fallos anotados. Sus 201
tiros no tienen resultados de tiro ni xG disponibles en esta importación: el
marcador final procede de los metadatos. No se usa `lead_to_goal` como si fuera
un gol individual. Los nombres/IDs de equipos y jugadores se sustituyen por
alias por partido; no se importan nombres, apellidos ni fechas de nacimiento.
La trazabilidad al partido público se conserva: es **seudonimización**.
Los campos originales de 104–106 × 68 m se normalizan explícitamente a 105 × 68 m.

Fuente y atribución: [Metrica Sports Sample Data](https://github.com/metrica-sports/sample-data).
Fuente adicional: [SkillCorner Open Data](https://github.com/SkillCorner/opendata),
licencia MIT conservada en `SKILLCORNER-LICENSE.txt`. Fuente fijada y hashes en
`skillcorner-source.json`; auditoría conjunta en `real-data-cloud-report.json`.
Revisión y SHA-256: `metrica-source.json`. Datos crudos/preparados: `.cache/metrica/`,
ignorados por Git. Los diez partidos sintéticos siguientes se conservan como
**historial separado**, con sus etiquetas sintéticas; no se han disfrazado de reales.

```powershell
python scripts/download_metrica.py
python scripts/prepare_metrica.py
node database/azure-sql/load-metrica.mjs
python scripts/download_skillcorner.py
python scripts/prepare_skillcorner.py
node database/azure-sql/load-skillcorner.mjs
node database/azure-sql/audit-metrica.mjs --all-real
python scripts/verify_real_data.py
```

El cargador añade IDs nuevos y publica en una transacción por partido. Rechaza
colisiones con otro origen. `real-data-migration.sql` admite observaciones reales
con procedencia explícita. No desactiva triggers ni reemplaza los datos existentes.

El esquema de 30 tablas está adaptado a SQL Server/Azure SQL, con 43 claves foráneas. `schema.sql` contiene todos los campos, claves, índices y reglas. `model.json` conserva el modelo revisado original; `build_schema.py` genera su adaptación ejecutable.

## Conexión

- Servidor: `sql-inside-game-01a160e1-ca.database.windows.net`
- Base: `inside-game`
- Región: Canada Central.
- Autenticación: Microsoft Entra, con la misma cuenta usada para Azure CLI. No hay contraseña SQL.
- Red: una regla de firewall para la IP pública del equipo que realizó la carga. Si cambia tu IP, debes actualizar esa regla; no abras el acceso a todas las direcciones.
- Cifrado: TLS, con validación del certificado.

Puedes conectarte desde una herramienta compatible con SQL Server y autenticación Entra. Para las consultas de aplicaciones, usa las vistas del esquema `analytics`. El rol `football_reader` tiene permiso de lectura sobre esas vistas. El contenedor de API/MCP usa su identidad administrada mediante `inside_game_cloud_reader`, miembro de ese rol, sin permisos administrativos ni de escritura.

## Coste configurado

Se eligió **Azure SQL Database, oferta gratuita**, General Purpose, Gen5, serverless, máximo 2 vCores, mínimo 0,5, 32 GB y backup local. La configuración importante es:

```text
useFreeLimit = true
freeLimitExhaustionBehavior = AutoPause
autoPauseDelay = 60 minutos
```

La oferta incluye 100.000 segundos de vCore, 32 GB de datos y 32 GB de backup al mes por base. Al agotar el cupo, esta base se pausa hasta el siguiente mes, en vez de facturar sobreconsumo. Esto puede limitar su disponibilidad. No se crearon servidores de API/MCP, réplicas, redes privadas ni recursos de cómputo adicionales.

Esta configuración corresponde a esta base; no representa el saldo de crédito ni los cargos de toda la suscripción. Oferta: [Microsoft Learn](https://learn.microsoft.com/en-us/azure/azure-sql/database/free-tier?view=azuresql).

## Historial: datos sintéticos de demostración

Todo el contenido se genera con la semilla `20261021`. No son partidos, personas ni estadísticas reales del repositorio Hudl.

| Contenido | Cantidad |
|---|---:|
| Competiciones / temporadas | 1 / 1 |
| Equipos / jugadores registrados | 4 / 56 |
| Partidos de 90 minutos | 10 |
| Eventos | 25.012 |
| Pases / tiros | 5.752 / 209 |
| Capturas 360 | 209 |
| Frames de tracking a 1 Hz | 54.020 |
| Posiciones de jugadores activos | 1.188.440 |
| Posiciones del balón | 54.020 |

Hay 22 jugadores activos por frame, dos períodos de 45 minutos y muestras de los extremos de ambos períodos. Cada evento tiene un enlace exacto a su frame. Hay tres sustituciones por equipo y partido: los 56 inscritos tienen intervalos reales de participación sintética. El tracking y las capturas cambian de identidad desde el segundo siguiente al cambio; no se atribuyen coordenadas en cancha a jugadores fuera de su intervalo activo.

`raw_payload`, `tracking_runs` y `config` identifican la procedencia sintética y la versión **3.0.0**. La revisión comprueba tanto coherencia como cobertura analítica. El campo heredado `statsbomb_xg` contiene un **xG de demostración**, calculado por distancia y ángulo. No es una predicción del modelo de StatsBomb ni una medida válida de rendimiento deportivo real.

El escenario representa amistosos de entrenamiento con dos tiempos de 45 minutos, cambios y sin tiempo añadido. Incluye intercepciones, quites, regates completos e incompletos, conducciones, recepciones, desposesiones, malos controles, bloqueos, despejes y duelos aéreos con ganador/perdedor relacionados. Se anotan córners y saques de banda tras salidas del balón, además de faltas, saques de meta y centro. Hay pases rasos y elevados y remates de cabeza y ambas piernas.

El balón sigue al poseedor, viaja desde cada pase hasta su recepción/intercepción, alcanza el final del tiro y tiene detenciones. Las acciones de contacto se comprueban con el tracking; las asistencias exigen un pase completado al rematador. También se auditan velocidades, aceleraciones y los intervalos de sustitución. Es una simulación preparada para demostraciones, sin distribuciones profesionales calibradas ni arbitraje completo. No simula la caminata hacia/desde el banco. Los escenarios no anotados y las limitaciones se detallan en [DATA-QUALITY.md](DATA-QUALITY.md).

La cobertura 360 es sintética de campo completo, no una cámara real. Los eventos se obtienen mediante una transformación afín de metros a 120 × 80 y rotación al equipo que actúa. La portería física mide 7,32 × 2,44 m; sus coordenadas normalizadas se derivan de esa transformación.

## Qué permite consultar

`queries.sql` contiene consultas ejecutables para:

1. Tiros, tiros a puerta, goles y xG por equipo.
2. Cuándo y dónde ocurrió cada tiro a puerta.
3. Posiciones de jugadores y balón en un segundo y período concretos.
4. Mapas de calor de jugadores, ponderados por segundos.
5. Entradas ganadas, manteniendo separados otros tipos de duelo.
6. Presiones y contrapresiones.
7. Jugadores cercanos al autor de un tiro.

Los tiros a puerta usan los resultados `Goal`, `Saved` y `Saved to Post`; se excluyen las tandas del período 5. La duración sumada de presiones puede contener solapamientos. `under_pressure` indica presión recibida.

[queries-coverage.sql](queries-coverage.sql) añade nueve consultas sobre cobertura por partido, intercepciones, regates, conducciones, quites, disputas aéreas, sustituciones, minutos y reanudaciones. [El catálogo de operaciones](../../docs/data-operations-catalog.md) relaciona preguntas analíticas, fuentes, cálculos y límites para diseñar las interfaces del agente de datos. Los tipos sin tabla especializada se almacenan en `events.details`; no necesitan tablas ficticias separadas.

El tracking utiliza metros sobre un campo fijo de 105 × 68; los eventos/capturas usan coordenadas de 120 × 80 orientadas al equipo que actúa. `tracking_periods.home_attacks_positive_x` permite transformar entre ambos sistemas. No se deben mezclar directamente.

La posición está almacenada **cada segundo**. Para tiempos intermedios es necesaria una consulta con interpolación explícita; una posición interpolada debe identificarse como tal. El esquema también admite datos ausentes mediante `position_status` y `sample_method`. Una captura 360 es una colección de coordenadas alrededor de un evento, no una imagen ni seguimiento continuo. Sus filas siguen siendo anónimas; la identidad procede del tracking.

## Integridad al adaptar PostgreSQL

SQL Server comprueba las FK inmediatamente y no tiene los triggers diferidos de PostgreSQL. Se añade `matches.data_status`:

1. El importador inserta un partido en estado `loading`, en orden de dependencias.
2. `statsbomb.publish_match` exige exactamente un local y un visitante, detalles obligatorios de los eventos, frames dentro del período y enlaces temporales válidos.
3. Sólo entonces cambia a `ready`. Las vistas `analytics` ocultan partidos incompletos.
4. Los partidos publicados y sus filas asociadas quedan bloqueados para cambios mediante triggers. Una corrección normal importa otra versión con nuevos identificadores. La reparación administrativa de esta demo conserva los identificadores mediante un respaldo y una transacción con bloqueo; no se habilita esta operación al rol lector.

`quality-rules.sql` añade controles al publicar: coherencia de asistencias, códigos de tiros y equipo de cada posesión. Para las versiones sintéticas 2.0.0 y 3.0.0 exige además marcadores coherentes con goles, cercanía en presiones/disputas y 22 jugadores más el balón en cada frame. Para 3.0.0 también exige las familias mínimas de acciones, seis sustituciones y actores activos. `audit-cloud.mjs` comprueba las reglas temporales y geométricas leyendo Azure; `audit-coverage.mjs` verifica variantes y relaciones efectivamente presentes.

Las FK compuestas conservan la pertenencia a partido/equipo, la inscripción del jugador y el tipo de evento. Un índice único filtrado limita los puestos activos 1–11 por equipo/frame sin impedir múltiples posiciones fuera de cancha con puesto nulo. Las FK se cargan con comprobación de restricciones habilitada.

Los usuarios de consultas necesitan sólo el rol lector. Las credenciales de administrador, como en cualquier base, permiten cambiar el DDL y deben reservarse para administración. Las cargas y publicaciones deben usar transacciones, como hace `synthetic.mjs`.

## API y MCP

La API y el MCP ya consultan esta base desde Azure Container Apps mediante una identidad administrada de lectura. El acceso de compañeros y agentes se protege con credenciales Bearer individuales, distintas de la identidad SQL. [Acceso y despliegue de la demo](../../docs/azure-demo.md); [estado del contenedor](../../deployment/cloud.json). El modelo relacional no requiere cambios por usar REST o MCP.

[Data API builder](https://learn.microsoft.com/en-us/azure/data-api-builder/overview) es una opción compatible con Azure SQL; también puede utilizarse un backend propio.

## Reproducir y verificar

Necesitas Node.js, Python y Azure CLI. `deployment.json` contiene exclusivamente identificadores y configuración, sin credenciales.

```powershell
cd database/azure-sql
npm install
az login
az account set --subscription 40baf6ea-db75-448e-8482-ec1d0449d05b
python build_schema.py
# Sólo sobre una base NUEVA y vacía:
npm run deploy
npm run seed
# Sobre la base ya cargada:
npm run validate
npm run audit
npm run audit:coverage
# Controles del generador y del propio auditor, sin cambiar Azure:
npm run audit:local
npm run audit:tests
```

Si Azure CLI no está en PATH, define `AZURE_CLI_PATH` con la ruta a `az.cmd`. Se obtiene un token de Azure SQL en memoria: no se guarda en archivos ni se imprime. `deploy` rechaza sobrescribir un esquema existente y `seed` rechaza sobrescribir partidos.

`seed-report.json` registra la carga; `validation-report.json` registra integridad y consultas; `realism-cloud-report.json` registra la coherencia de las filas leídas de Azure; `coverage-cloud-report.json` registra cobertura, variantes y ejemplos analíticos ejecutados. `audit-tests-report.json` demuestra que el auditor detecta errores provocados. `azure-state.json` registra el recurso. La revisión y sus límites están en `DATA-QUALITY.md`. Los respaldos están en `backups/`, excluidos de Git. `scenario-v3.mjs` y `load-v3.mjs` son el generador/cargador actuales; los archivos v2 se conservan como referencia histórica.
