# Estructura inicial del repositorio

El repositorio es `Inside-the-game-Developer-Hackathon`. El paquete Python se
llama `inside_game`; el nombre `football_mas` del texto de referencia no se usa.

```text
Inside-the-game-Developer-Hackathon/
├── src/
│   └── inside_game/
│       ├── __init__.py
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── interpreter.py
│       │   ├── data_agent.py
│       │   ├── contracts.py       # Mensajes del agente de datos
│       │   ├── sports_analyst.py
│       │   ├── dashboard_builder.py # Reexporta ambos ejecutores
│       │   ├── page_builder.py      # MCP + revisiones + texto del analista
│       │   ├── insight_contracts.py # Mensajes y patches HTTP
│       │   ├── http_api.py          # HTTP autenticado
│       │   └── report_store.py      # Artefactos privados
│       │   └── insights_agent/    # Agente de insights (docs/insights-agent.md)
│       │       ├── agent.py       # InsightsAgent.ask(): pregunta o intención -> respuesta
│       │       ├── __main__.py    # CLI de conversación
│       │       ├── contracts.py   # InsightIntent y plan resuelto
│       │       ├── templates.py   # Recetas por plantilla del renderer
│       │       ├── profiles.py    # Qué puede mostrar cada fuente (+ source_profiles.json)
│       │       ├── resolver.py    # Intención -> consultas exactas, sin LLM
│       │       ├── composer.py    # Plan -> evidencia -> MCP de insights -> HTML
│       │       ├── planner.py     # Pregunta -> InsightIntent (LLM)
│       │       └── remote_data.py # Cliente A2A del agente de datos
│       ├── a2a_agents/            # Servidores, clientes y contratos A2A (docs/a2a.md)
│       │   ├── common.py          # Token y apertura de clientes
│       │   ├── contracts.py       # ExecutePlanRequest / PlanResult
│       │   ├── data_server.py     # Agente de datos: skill execute_plan
│       │   ├── insights_server.py # Agente de insights: skill ask_insight
│       │   └── insights_client.py # Cliente del agente de insights
│       ├── insights/              # Renderer de 30 recetas y su MCP
│       ├── local_env.py           # Lectura de entorno y .env.local
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── evidence_client.py # Plan de consultas -> evidencia validada
│       │   ├── synthetic_db.py
│       │   └── topology.py
│       ├── providers/
│       │   ├── __init__.py
│       │   ├── models.py
│       │   └── opencode.py         # Console/Zen o Go; planes y credenciales separados
│       ├── contracts.py
│       ├── analytics.py           # Definiciones deterministas de métricas
│       ├── service.py             # Registro de operaciones y consultas
│       ├── settings.py
│       ├── errors.py
│       ├── sql/                   # Plantillas SELECT parametrizadas
│       ├── orchestrator.py
│       ├── api.py
│       ├── mcp_server.py          # Tools MCP sobre las rutas fijas de la API
│       ├── access.py              # Credenciales individuales, caducidad y permisos
│       ├── cloud.py               # API + MCP con identidad preservada en Azure
│       ├── cli.py
│       └── data_agent_cli.py      # Texto/JSON -> evidencia JSON
├── frontend/
│   └── src/
│       └── components/
├── prompts/
├── tests/
├── docs/
│   └── repository-structure.md
├── database/
│   └── azure-sql/                  # Esquema, datos y herramientas existentes
├── drafts/                        # Referencias existentes
├── AGENTS.md
├── pyproject.toml
├── README.md
└── .gitignore
```

La API, los contratos, el servicio de consultas, el acceso SQL y los cálculos
espaciales están implementados. `pyproject.toml` define dependencias y el comando
`inside-game-api`. Instalación y uso: [api.md](api.md).

El servidor MCP está implementado con SDK oficial y transportes stdio y Streamable HTTP.
El contenedor público de Azure usa credenciales individuales y lectura SQL con identidad
administrada. Uso: [mcp.md](mcp.md) y [azure-demo.md](azure-demo.md). El agente de datos,
su prompt en `prompts/data_agent.md`, proveedor Azure OpenAI y cliente MCP están
implementados; uso y límites en [data-agent.md](data-agent.md). El agente de
insights está en `agents/insights_agent/` ([insights-agent.md](insights-agent.md)): disponibilidad por
fuente en [insights-availability.md](insights-availability.md) y comunicación
A2A con el agente de datos en [a2a.md](a2a.md). El intérprete, analista,
dashboard builder y orquestación mantienen sus módulos reservados. La infraestructura y los datos de Azure SQL
se conservan en `database/azure-sql/`. Los scripts de despliegue están en `scripts/` y los identificadores públicos del alojamiento en `deployment/cloud.json`.
