# Revisión de credenciales y Ollama — 26 de octubre de 2026

Se revisaron `main` (`a51866d`) y `origin/feature/ollama-provider` (`d33affa`).
La revisión usó una copia aislada de los archivos de la rama: no se cambió la
rama activa ni `.env.local`. No se ejecutaron modelos ni se cambió facturación.

## Configuración actual

| Capa | Autenticación configurada | Estado comprobado |
|---|---|---|
| API y MCP deportivos publicados en Azure | Bearer individual; claves externas a Git y registro de hashes en el servidor | `team-collaborator-01` y `agent-data`: HTTP 200 en `/api/whoami`. La primera comprobación de `agent-data` agotó 15 s; la repetición pasó. |
| Cliente del agente de datos → MCP | `INSIDE_GAME_DATA_MCP_URL` + `INSIDE_GAME_DATA_MCP_CREDENTIAL_FILE`; alternativa: `INSIDE_GAME_DATA_MCP_KEY` | `.env.local` referencia el archivo privado `agent-data.json`; no contiene la clave cruda. La variable directa prevalece sobre el archivo. |
| Agentes HTTP propios, puerto 8085: Data, Insights y analista | `INSIDE_GAME_AGENT_CREDENTIALS_JSON`, o registro derivado del archivo individual `agent-data.json` | No hay registro explícito configurado en el archivo local ni en el proceso de revisión. El arranque usa el archivo de `agent-data`; reconoce esa identidad, no automáticamente todas las personas autorizadas en la API. El Bearer entrante se delega a Data/Insights/MCP. |
| Servidores A2A SDK, puertos 8010/8020 | `INSIDE_GAME_A2A_TOKEN` opcional en loopback; necesario con ≥32 caracteres fuera de loopback | No configurado en `.env.local` ni en el proceso de revisión. Es una credencial distinta del Bearer de la API. Los servidores locales siguen usando la credencial API para consultar datos. |
| Modelo activo | `INSIDE_GAME_MODEL_PROVIDER=opencode-go`, `beam-free`, `cli_session` | Usa la sesión del CLI fuera del repo. `INSIDE_GAME_OPENCODE_FREE_ONLY=1`. No se hizo inferencia ni se comprobó la vigencia de esa sesión durante esta revisión. La clave antigua de OpenCode no es un fallback. |
| Azure OpenAI | Endpoint/despliegue vacíos en la configuración local activa | No seleccionado. Las variables de autenticación Azure conservadas no seleccionan ese proveedor. |
| SQL | Identidad administrada del contenedor; Azure CLI/Entra para la vía local | Consumir API/MCP remotos no requiere entregar credenciales SQL ni acceso administrativo de Azure. |
| GitHub Actions | Dos repository secrets y tres variables | Se verificó la presencia de `INSIDE_GAME_API_KEY`, `INSIDE_GAME_DATA_MCP_KEY`, `INSIDE_GAME_API_URL`, `INSIDE_GAME_MCP_API_URL` e `INSIDE_GAME_DATA_MCP_URL`; no se extrajeron valores secretos ni se ejecutó Actions. |

Las credenciales privadas `agent-data`, `team-collaborator-01` y `team-owner`
declaran caducidad el **6 de noviembre de 2026, 14:28:18 de Colombia**. Sólo las
dos primeras se comprobaron contra el servicio en esta revisión.

El dashboard y el runtime de Insights usan `DashboardConfig`: pueden leer la
clave directa de API/MCP o el archivo privado. Por eso no es necesario copiar
una clave nueva para cambiar el modelo. El código fuente de la configuración
indica cómo arrancar cada servicio; esta revisión no inspecciona el entorno
interno de procesos que ya estén ejecutándose.

## Rama Ollama

La rama añade `providers/ollama.py`, lo conecta a `create_model()` y adapta
la etiqueta del modelo de Insights. Se selecciona explícitamente; no reemplaza
la configuración OpenCode existente. `main` todavía no incluye ese proveedor.

Ollama local utiliza `http://127.0.0.1:11434/v1/chat/completions` sin cabeceras
de autenticación. No hay que introducir allí las claves deportivas ni las de
Azure/OpenCode. Los Bearer de API/MCP y del HTTP de agentes siguen siendo
necesarios aunque el LLM sea local.

El proveedor acepta loopback y direcciones IP privadas/LAN/Tailscale; no acepta
un nombre DNS de equipo arbitrario. No configura un servidor, descarga modelos
ni cambia parámetros del proceso de Ollama.

### Verificación y límites

- **72 pruebas simuladas pasaron**: `test_ollama_provider.py`, `test_local_env.py`,
  `test_insights_agent_planner.py` y `test_data_agent.py`. El primer intento bajo
  el sandbox quedó detenido al entrar en pruebas asíncronas; se interrumpió y
  se repitió sin esa restricción. Los mocks no llaman a un proveedor real.
- No se encontró `ollama` en PATH ni un proceso Ollama en esta comprobación;
  `GET http://127.0.0.1:11434/api/tags` no logró conectar, también fuera del
  sandbox. No se validó inferencia en este equipo.
- El timeout del proveedor (300 s) no amplía el plazo de los agentes: Data HTTP
  tiene 40 s por defecto y 45 s máximo; el planner de Insights tiene 40 s,
  Insights completo 55 s y el analista 45 s. Un arranque en frío puede caducar
  aunque el proveedor siga dentro de su límite. Para QA local, calentar antes
  o modificar y probar los límites de los ejecutores.
- El modelo por defecto es `qwen3:30b-a3b-instruct-2507-q4_K_M`; las cifras de
  memoria/rendimiento de la documentación de la rama corresponden al equipo de
  su autor, no a una medición de este equipo.
- La documentación registra una selección incorrecta de herramienta para una
  pregunta de goles. Sus tres pruebas iniciales no ejecutaron el MCP real.
  Las pruebas unitarias aprobadas aquí tampoco equivalen a QA del corpus ni a
  validar la precisión deportiva del modelo.
- Usar un modelo instalado que ejecute inferencia local. Un endpoint local de
  Ollama también puede servir como acceso a modelos cloud si se configuran;
  el host loopback por sí solo no confirma ejecución local ni gratuidad.

## Perfil local preparado

Se creó `.env.ollama.local`, ignorado por Git. Contiene el proveedor, endpoint,
modelo de ejemplo de la rama y URLs deportivas. Conserva la referencia al archivo
privado existente; no copia claves y **no se ha activado**.

Una vez disponible el código de `feature/ollama-provider` en el checkout y con
Ollama/modelo instalados, cargar ese perfil sólo en la terminal de la prueba:

```powershell
foreach ($line in Get-Content -LiteralPath .env.ollama.local) {
    if ($line -match '^\s*(INSIDE_GAME_[A-Z_]+)\s*=(.*)$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim(), 'Process')
    }
}
```

Después, escoger una de estas vías:

```powershell
# Agente de datos CLI; conserva el perfil del proceso.
.\.venv\Scripts\python.exe -m inside_game.data_agent_cli --text "Describe la cobertura del conjunto de datos"

# Página de Insights con API deportiva remota y modelo local.
.\.venv\Scripts\python.exe -m inside_game.agents.insights_agent.web --port 8030

# HTTP propio con Data, Insights y analista, y su Bearer individual.
.\.venv\Scripts\python.exe -m inside_game.agents_cli --port 8085
```

No pasar `--azure-model` a la página si se quiere Ollama: esa opción selecciona
Azure explícitamente. `scripts/start-data-agent.ps1` vuelve a cargar `.env.local`
y puede reemplazar el perfil del proceso por OpenCode; usar el CLI Python directo
como en este ejemplo. Los servidores SDK A2A también necesitan las variables del
modelo en el proceso; no todos sus entrypoints cargan `.env.local` automáticamente.

Antes de probar preguntas, comprobar `ollama list`, `ollama ps` y el contexto
del servidor. La rama documenta un rechazo con 16.384 tokens y sus pruebas con
40.960 tokens: el prompt y las 34 herramientas son grandes. Configurar el
contexto en el servidor Ollama, no en las credenciales del proyecto.

Referencias: [rama y configuración del autor](https://github.com/luis-pl/Inside-the-game-Developer-Hackathon/blob/feature/ollama-provider/docs/ollama.md),
[autenticación de Ollama](https://docs.ollama.com/api/authentication),
[API compatible](https://docs.ollama.com/api/openai-compatibility) y
[contexto](https://docs.ollama.com/context-length).
