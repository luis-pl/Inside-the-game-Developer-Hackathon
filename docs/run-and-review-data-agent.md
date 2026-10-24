# Ejecutar el visor y probar el agente de datos

Ejecuta los comandos desde la raíz de este repositorio en PowerShell. En este
equipo ya existen `.venv`, las dependencias del frontend y `.env.local`.
Las credenciales permanecen en archivos privados externos al repositorio.

## Ver los partidos

```powershell
.\scripts\start-dashboard.ps1
```

Abre <http://127.0.0.1:8080/>. Mantén esa terminal abierta; Ctrl+C detiene el visor.
El launcher compila el frontend y elige Node compatible; también admite
`-NodePath "RUTA/node.exe"` y `-PythonPath "RUTA/python.exe"`.
El visor consulta la API remota configurada desde su backend local. No necesita
arrancar SQL, otra API local ni el modelo de lenguaje para mostrar partidos.

## Consultar con Beam Free

En otra terminal:

```powershell
.\scripts\start-data-agent.ps1 -ShowTools -Text "Del partido 900011, recupera todos los tiros con momento y coordenadas. Conserva la procedencia y los campos ausentes." -OutputFile ".temp/prueba-agente.json"
$r = Get-Content .temp/prueba-agente.json -Raw -Encoding UTF8 | ConvertFrom-Json
$r | Select-Object status, model, model_turns, tool_calls, total_tokens
$r.notes
$r.evidence | Select-Object evidence_id, operation, arguments
```

`-ShowTools` muestra operaciones, tiempos y errores en la terminal; la evidencia
completa queda en el JSON. Para verla abre `.temp/prueba-agente.json` en el editor.
También puedes omitir `-OutputFile` para imprimir toda la respuesta.

Este es el agente de datos, cuya salida contractual es evidencia JSON para los
otros agentes. Cada invocación es independiente: no hay memoria de una pregunta
anterior. Si devuelve una aclaración, envía una nueva solicitud con el contexto
completo. Los otros agentes y la comunicación A2A siguen pendientes.

Cambiar `prompts/data_agent.md` afecta a la próxima ejecución local, sin compilar.
El resultado incluye `prompt_sha256` para identificar el texto exacto utilizado.
La comprobación de precio cero se realiza antes de cada inferencia. Si falla o
expira la sesión CLI, el agente se detiene: no cambia de modelo ni de plan.

Ejemplos para variar la solicitud:

- "En el partido 900001, equipo 1, dame los duelos aéreos ganados y las intercepciones, con sus eventos." (historial sintético).
- "Dame todas las posiciones observadas de los primeros diez segundos del primer tiempo del partido real 900011 a 5 Hz."
- "Del partido real 900101 necesito tiros, ubicaciones y xG; indica qué campos no existen."
- "Necesito el posicionamiento de un partido, pero no sé cuál." (debe pedir aclaración).

Para una entrada estructurada, usa `-RequestFile solicitud.json`. `request_text`
es obligatorio; `context` admite IDs de partidos, equipos, jugadores y alcance.
El contrato y los códigos de salida están en [data-agent.md](data-agent.md).

## Repetir la revisión con el modelo real

```powershell
.\.venv\Scripts\python.exe scripts/verify_data_agent.py --env-file .env.local --cases-file tests/fixtures/data_agent_review_cases.json --report .temp/review.json --results-dir .temp/review-results
```

Prueba 18 solicitudes con el catálogo completo, Beam Free, MCP y SQL reales.
El informe registra el hash del prompt, operaciones ejecutadas, argumentos,
estados y cotejo directo de la evidencia. Los JSON completos quedan en la carpeta
indicada; no contienen credenciales pero pueden ser grandes. No subir resultados
de sesión de `.temp` a Git sin revisarlos.

Las pruebas locales del ejecutor se ejecutan con:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

No sustituyen la evaluación lingüística real. Una pasada de 18 ejemplos tampoco
garantiza cualquier formulación posible o disponibilidad permanente del servicio.

[Hallazgos y resultados de la revisión](data-agent-review.md).
