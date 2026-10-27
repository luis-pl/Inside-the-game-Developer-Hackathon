# Intérprete y espacio de análisis

El intérprete recibe texto, contexto seleccionado y las últimas intervenciones.
Usa Beam Free con el mismo proveedor Go y la política `FREE_ONLY=1` existente.
Cada petición conserva su UUID durante las llamadas al modelo. Su prompt vive en
`prompts/interpreter.md`; el contrato `Interpretation` sólo permite crear,
modificar, aclarar, mostrar el catálogo o responder orientación y conceptos mediante
`answer`. `answer_topic` admite `general`, `welcome`, `xg` y `voronoi`. No admite
SQL, código o destinos externos.

## Ejecutar

Con las dependencias privadas del proyecto ya configuradas:

```powershell
# Compilar una vez, o después de editar el frontend. Node según frontend/package.json.
cd frontend
npm ci
npm run build
cd ..
.venv\Scripts\python.exe -m inside_game.workspace --local-demo --port 8090
```

Abrir <http://127.0.0.1:8090> y pulsar **Entrar a la demo local**. Los cuatro agentes,
sus comunicaciones HTTP y la interfaz funcionan con ese único proceso. Las API
deportiva/MCP y SQL existentes siguen siendo remotas. `/viewer` conserva el visor
de posiciones. El CLI clásico de dashboard mantiene su entrada de visor.

`--local-demo` es una opción explícita, limitada al propio equipo. Usa en el servidor
la credencial individual agent-data configurada; no entrega esa clave al navegador.
Sin esa opción el formulario solicita una credencial individual de equipo válida
para el registro del servicio agéntico. Compartir el despliegue requiere configurar
ese registro con los miembros autorizados; no basta con escribir un correo.
Este CLI escucha únicamente en loopback; esta entrega no publica un nuevo servicio
en Azure ni cambia facturación o el modelo autorizado.

## Flujo

1. Se carga el catálogo mediante la operación fija `list_matches` de la API de
   Data, sin inferencia del modelo para obtener esos metadatos, y se conserva
   cinco minutos por titular. El endpoint del chat mantiene su contrato público.
2. El usuario selecciona un partido o lo identifica por texto. Si falta contexto,
   el intérprete formula como máximo una pregunta concreta; los IDs propuestos se
   validan contra el catálogo. Un saludo o una explicación conceptual no exige
   crear una página ni elegir partido.
3. Una creación delega a Data, entrega la evidencia original al analista y usa el
   flujo analista ↔ Insights → MCP de gráficos para publicar texto y visualizaciones.
4. Una modificación aplica el patch a la versión vigente. El analista revisa el
   payload de esa misma página y sustituye la nota anterior. No crea otra página
   para analizarla. Si falla la narración, el informe no conserva una nota vieja
   como si se hubiera recalculado.
5. El chat permite descargar HTML y trazabilidad. El iframe está aislado, sin
   acceso al origen del chat ni permiso de red; los gráficos conservan su JS local.

Los trabajos son asíncronos y el frontend consulta su estado. Se muestran etapas
reales, sin porcentajes o avances simulados. Sólo se permite una ejecución por
conversación y cuatro globales. Un mismo request_id no ejecuta dos veces la misma
solicitud y se rechaza si se reutiliza con otro texto.

`concept_reply` revisa las respuestas de bienvenida, xG y Voronoi; `general`
conserva el borrador del intérprete. La bienvenida propone ocasiones, pases y
espacios. xG se explica como probabilidad según un modelo, con límites sobre su
disponibilidad y su carácter ilustrativo en los datos sintéticos. Voronoi expresa
cercanía geométrica, sin convertirla en control probado. La respuesta de catálogo
conserva su introducción, ofrece hasta cinco partidos por nombres sin IDs y remite
al selector para la lista completa. Estas rutas responden en la conversación sin
crear ni modificar el informe.

Después de publicar, `report_reply` reutiliza hasta dos afirmaciones ya validadas
de la primera sección analítica útil, omitiendo secciones dedicadas a contexto,
alcance o fuentes. No vuelve a calcular cifras ni sustituye la respuesta deportiva
por un recuento de gráficos. Al resumir, si todos los facts citados son sintéticos,
lo declara al comienzo. Si el resultado es parcial, añade el alcance limitado;
una edición que reutiliza análisis confirma que los datos y la lectura se conservan.

El prompt del analista prioriza hallazgos en una primera sección «Lo más importante»
o una conclusión deportiva específica. El texto del lector evita repetir etiquetas
como «Observación» en cada afirmación; se conservan `kind`, facts y citas en sus
contratos y trazas. `insights/analysis_note.py` presenta apartados con prosa legible:
procedencia y primera limitación quedan visibles, el resto del alcance se pliega
en «Alcance y límites» y las referencias en «Fuentes y referencias».

## Interacción y cambios de versión

Historial y chat se ajustan con arrastre o teclado. Los separadores exponen rango y
valor accesibles; flechas cambian 10px, Mayús + flechas 40px, Inicio/Fin los extremos
permitidos y doble clic el ancho inicial dentro del espacio disponible. El historial
puede contraerse en escritorio y el chat moverse al otro lado del documento.
«Restablecer paneles» devuelve historial expandido, 220px de historial, 350px de chat
y chat a la derecha, con ajuste posterior al espacio disponible. Sólo estas
preferencias y el tema se guardan en localStorage. En móvil se alternan informe y
chat, y el historial abre como cajón modal.

La espera muestra etapas y segundos reales, conserva el informe ya cargado y no
promete un plazo. El chat mantiene la posición al leer mensajes anteriores y ofrece
«Nuevos mensajes». Una revisión publicada muestra un resumen de gráficos añadidos,
actualizados o retirados, o del cambio exclusivo de título/análisis, junto a su versión.
«Ver cambios», «Ir a los gráficos» y «Leer análisis» sitúan el foco en el documento.

`report-document.ts` añade un puente limitado de `postMessage`: el iframe verifica
que el emisor sea su padre y que el token coincida antes de aceptar destinos de
foco definidos. El padre usa `*` como origen destino porque el sandbox tiene origen
opaco; no se habilita `allow-same-origin`. El CSP bloquea conexiones de red y
conserva los hashes de scripts del HTML original, añadiendo un nonce efímero al
script propio del puente. El padre sólo marca el documento disponible después
del mensaje `inside-game-ready` con ventana emisora y token coincidentes. El
puente transmite foco y confirmación del DOM, sin HTML, URLs o credenciales.

Los fallos se traducen a mensajes recuperables; el código queda en «Detalles de la
ejecución». Según la causa se ofrece «Reintentar solicitud» o «Completar análisis».
Si falla cargar una nueva versión se conserva el HTML ya mostrado. La condición
`hasScopedAnalysis` reconoce específicamente el último análisis `partial` con
`issues: []` y gráficos `complete` para evitar ofrecer un reintento innecesario de
ese alcance. El frontend conserva el texto deportivo recibido del servidor, sin
sobrescribirlo por una confirmación genérica, ni convertir el estado en análisis
completo.

## Contratos HTTP

Rutas Bearer autenticadas en el servicio de agentes:

| Método y ruta | Uso |
|---|---|
| GET/POST `/a2a/v1/conversations` | Listar/crear conversaciones del titular |
| GET `/a2a/v1/conversations/{id}` | Mensajes, estado, informe y trazas |
| POST `/a2a/v1/conversations/{id}/messages` | Texto, request_id y contexto opcional; devuelve 202 |
| GET `/a2a/v1/conversations/{id}/page` | HTML de la versión seleccionada |
| GET `/a2a/v1/chat-catalog` | Partidos disponibles |

El navegador usa el BFF `/workspace-api`, una cookie HttpOnly SameSite=Strict de
una hora y una cabecera de intención en mutaciones. El BFF sólo reenvía rutas
permitidas al servicio interno. Las claves viven en memoria del servidor y no se
guardan en localStorage, cookies, URLs, respuestas ni el bundle. Las conversaciones
se aíslan por titular, no por una etiqueta que envíe el modelo.

## Límites y verificación

Conversaciones y páginas están en memoria: reiniciar sin un respaldo y restauración
explícitos las elimina.
Máximo 20 conversaciones por titular, 200 globales, 60 mensajes por conversación y
las tres últimas trazas. Caducan tras una hora sin terminar otra ejecución. El
almacén de informes mantiene sus límites propios. El HTML descargado sí se conserva.

Antes de detener una demo local, sin trabajos en curso, se puede guardar un respaldo:

```powershell
.venv\Scripts\python.exe scripts\backup_workspace.py --output .temp\workspace-user-backup.json
```

Después se inicia la demo restaurando ese archivo explícitamente:

```powershell
.venv\Scripts\python.exe -m inside_game.workspace --local-demo --port 8090 --restore .temp\workspace-user-backup.json
```

El exportador consulta la instancia local del puerto 8090 con la identidad privada
configurada en el servidor. Guarda conversaciones y la versión disponible de cada
informe con sus metadatos y HTML; no exporta el historial completo de revisiones.
Rechaza trabajos en curso y comprueba que la clave usada no aparezca en el archivo.
El respaldo contiene mensajes y evidencia: conservarlo localmente. La restauración
requiere `--local-demo`, valida versión, titular y referencias de evidencia antes de
incorporar los elementos, y renueva su caducidad en memoria a una hora. No reejecuta
los trabajos ni habilita persistencia automática.

El límite total de un trabajo es 110 s; no es una promesa de generar toda pregunta
en menos de un minuto. El catálogo, la complejidad y la latencia de los servicios
influyen. El prompt y las validaciones reducen errores, sin garantizar que toda
interpretación en lenguaje natural sea perfecta.

En el caso real `real11ready`, la ejecución observada tardó 93,45 s: los gráficos
quedaron listos y la lectura del analista fue `partial` sin issues por el alcance
top 5. Es evidencia de ese caso, no de análisis completo ni de latencia inferior
a un minuto para cualquier solicitud.

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts\qa_workspace.py
```

La QA real comprueba creación de shot_map + xg_story, cambio de título en la misma
página conservando los bloques, y explicación de xG ausente en Metrica. Conserva
solicitudes, páginas y trazas en `.temp/workspace-qa/`, sin cookies ni claves.

La iteración de conversación pasó 435 pruebas Python, 46 del frontend y una prueba
acotada de siete solicitudes con Beam Free, conservada en
`.temp/sports-conversation-final/responses.json`. Esta última comprueba decisiones
y respuestas del intérprete; no ejecuta las delegaciones de creación/modificación
ni certifica la disponibilidad final de todos sus gráficos. La QA adicional creó
un informe completo en 35,22 s y conservó los dos bloques al editarlo en 4,983 s.
La falta de xG de Metrica se respondió con `answer`, sin página ni valores
inventados. Resultados en `docs/sports-conversation-verification.json`. Los fallos
de tiempo previos y el caso de 93,45 s siguen siendo antecedentes vigentes; estos
resultados puntuales no acreditan latencia estable para cualquier solicitud.
