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
│       │   ├── dashboard_builder.py # Agente de insights con MCP
│       │   ├── insight_contracts.py # Mensajes y patches de páginas
│       │   ├── http_api.py          # Data e insights por HTTP
│       │   └── report_store.py      # Artefactos privados y revisiones
│       ├── tools/
│       │   ├── __init__.py
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
insights, su prompt, MCP y comunicación HTTP con data están implementados:
[insight-agent.md](insight-agent.md). El intérprete, analista y orquestador general
conservan sus módulos reservados. El frontend Topology Lab está implementado;
el HTTP de agentes es un protocolo propio. La infraestructura y los datos de Azure SQL
se conservan en `database/azure-sql/`. Los scripts de despliegue están en `scripts/` y los identificadores públicos del alojamiento en `deployment/cloud.json`.
