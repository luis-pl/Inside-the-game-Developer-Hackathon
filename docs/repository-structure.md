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
│       │   ├── sports_analyst.py
│       │   └── dashboard_builder.py
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── synthetic_db.py
│       │   └── topology.py
│       ├── providers/
│       │   ├── __init__.py
│       │   └── models.py
│       ├── contracts.py
│       ├── orchestrator.py
│       ├── api.py
│       └── cli.py
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

Los nuevos módulos Python sólo describen su responsabilidad futura. Las carpetas
sin contenido usan `.gitkeep` para poder conservarlas en Git. `pyproject.toml`
define el paquete sin dependencias de ejecución ni comandos publicados.

Los agentes, contratos, prompts, herramientas, proveedores, API, CLI, frontend e
integraciones MCP/A2A se implementarán en las siguientes etapas. La infraestructura
y los datos de Azure SQL existentes se mantienen en `database/azure-sql/`.
