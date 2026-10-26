# Intérprete y espacio de análisis

El intérprete recibe texto, contexto seleccionado y las últimas intervenciones.
Usa Beam Free con el mismo proveedor Go y la política `FREE_ONLY=1` existente.
Cada petición conserva su UUID durante las llamadas al modelo. Su prompt vive en
`prompts/interpreter.md`; el contrato `Interpretation` sólo permite crear,
modificar, aclarar o mostrar el catálogo. No admite SQL, código o destinos externos.

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

1. Se carga el catálogo real mediante Data y se conserva cinco minutos por titular.
2. El usuario selecciona un partido o lo identifica por texto. Si falta contexto,
   el intérprete pregunta; los IDs propuestos se validan contra el catálogo.
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

Conversaciones y páginas están en memoria: reiniciar el proceso las elimina.
Máximo 20 conversaciones por titular, 200 globales, 60 mensajes por conversación y
las tres últimas trazas. Caducan tras una hora sin terminar otra ejecución. El
almacén de informes mantiene sus límites propios. El HTML descargado sí se conserva.

El límite total de un trabajo es 110 s; no es una promesa de generar toda pregunta
en menos de un minuto. El catálogo, la complejidad y la latencia de los servicios
influyen. El prompt y las validaciones reducen errores, sin garantizar que toda
interpretación en lenguaje natural sea perfecta.

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts\qa_workspace.py
```

La QA real comprueba creación de shot_map + xg_story, cambio de título en la misma
página conservando los bloques, y explicación de xG ausente en Metrica. Conserva
solicitudes, páginas y trazas en `.temp/workspace-qa/`, sin cookies ni claves.
