# Comunicación A2A entre agentes

Dos agentes expuestos por A2A (`a2a-sdk` 1.2.x, JSON-RPC), en
`src/inside_game/a2a_agents/`:

```text
cliente (CLI, intérprete, UI)
  └─ A2A ask_insight ──► agente de insights :8020
                           └─ A2A execute_plan ──► agente de datos :8010 ──► API Azure
```

`common.py` reúne la autenticación por token y la apertura de clientes.

## Agente de datos: skill `execute_plan`

```powershell
.\.venv\Scripts\python.exe -m inside_game.a2a_agents.data_server --port 8010
```

- AgentCard público: <http://127.0.0.1:8010/.well-known/agent-card.json>.
- Entrada `ExecutePlanRequest`: hasta 60 consultas exactas `{key, operation, arguments}`
  de las operaciones registradas. Salida `PlanResult`: por consulta, IDs de
  evidencia o código de error, y la evidencia original con procedencia.
- Sin LLM: valida, pagina y comprueba identidad y procedencia de cada respuesta
  con el mismo motor que el cliente local (`tools/evidence_client.py`).
- Envuelve el acceso a datos sin modificar `agents/data_agent.py`. La skill en
  lenguaje natural del agente de datos se publicará cuando haya modelo.
- Un mensaje que no es un plan válido termina en `REJECTED`; un fallo interno en
  `FAILED` con código, sin detalles. Los errores por consulta (p. ej.
  `SOURCE_FIELD_UNAVAILABLE`) viajan en su resultado sin ocultar los demás.

## Contratos como JSON en texto

Los mensajes viajan como una parte de texto `application/json`, no como
DataPart: un DataPart se transporta como `google.protobuf.Value` y convierte
los enteros en double (`900001` → `900001.0`), lo que rompería los IDs estrictos.
`tests/test_a2a_transport.py` fija este comportamiento del SDK.

## Autenticación

Si `INSIDE_GAME_A2A_TOKEN` existe (entorno o `.env.local`), el endpoint JSON-RPC
exige `Authorization: Bearer <token>`, comparado en tiempo constante; el
AgentCard sigue siendo público. Sin token el servidor sólo escucha en loopback.
El cliente lee el mismo token y nunca lo pone en la URL.

## Cliente en el agente de insights

`connect_data_agent(url)` descubre el AgentCard y devuelve un cliente con la misma
interfaz que el local (`fetch`, `query`, `run`, `evidence`): resolvedor y
compositor no cambian. Las consultas sin caché de un `run` viajan en un mensaje;
las consultas se renumeran para toda la sesión (q1, q2…), así dos evidencias
nunca comparten ID en un informe, y se revalidan con el contrato local. El MCP
de insights conserva el contexto del partido para nombrar a los equipos.

```powershell
.\.venv\Scripts\python.exe -m inside_game.agents.insights_agent --data-agent-url http://127.0.0.1:8010 --intent '{"template_id": "player_dossier", "match_id": 900101, "player_id": 10102}'
```

Verificado el 25 de octubre contra la API de Azure: ficha de jugador
(SkillCorner), episodio táctico (sintético) e informe libre (Metrica) dieron los
mismos bloques y descartes que el cliente local, con 2–4 mensajes A2A por
intención. En caliente, la ficha tarda 3,4 s; la primera consulta tras
inactividad tardó 91 s por el arranque de la base serverless.

## Agente de insights: skill `ask_insight`

```powershell
.\.venv\Scripts\python.exe -m inside_game.a2a_agents.insights_server --port 8020 --data-agent-url http://127.0.0.1:8010
```

- Entrada `AskRequest` (JSON): `question` o `intent`, y `previous` (el `next` de
  la respuesta anterior; el servidor no guarda sesiones).
- Artefactos: `answer` (`InsightAnswer`, JSON pequeño) y `report` (HTML), éste
  sólo si el cliente acepta `text/html` en `accepted_output_modes`.
- Estados: informe o rechazo → `COMPLETED`; aclaración → `INPUT_REQUIRED`;
  error de dominio → `FAILED` (con `answer` y códigos); fallo interno inesperado →
  `FAILED` con `INSIGHTS_AGENT_FAILED` (mensaje genérico, sin detalles); mensaje
  que no es un AskRequest → `REJECTED`.
- Un agente y un cliente de datos por petición: sin caché ni estado compartidos
  entre usuarios. Mismo token que el agente de datos. El agente de datos debe
  estar arrancado antes: el servidor descubre su AgentCard al iniciar.
- Los dos servidores conservan sólo las 16 últimas tareas terminadas
  (`BoundedTaskStore`): el almacén del SDK guardaría para siempre cada informe o
  plan con sus megabytes de artefactos.
- Modelo sólo si `INSIDE_GAME_MODEL_PROVIDER` está configurado explícitamente; si
  no, las preguntas en texto responden `MODEL_UNAVAILABLE` y las intenciones
  funcionan igual.
- Cliente: `a2a_agents/insights_client.py` (`connect_insights_agent`), con la
  misma interfaz `ask()` → `AskResult` que el agente local.

```powershell
.\.venv\Scripts\python.exe -m inside_game.agents.insights_agent --insights-agent-url http://127.0.0.1:8020 --intent '{"template_id": "match_overview", "match_id": 900011}'
```

Verificado el 25 de octubre con los dos servidores y la API de Azure: tiros y red
de pases del Equipo B (Metrica 2, filtrados a ese equipo), pregunta sin modelo
(`MODEL_UNAVAILABLE`), ficha de jugador (SkillCorner, 5 piezas y 2 descartes) y
partido inexistente (`MATCH_NOT_FOUND`). Seis pruebas en memoria cubren la cadena
completa, estados, aclaración en dos turnos, rechazo, HTML opcional y token.
