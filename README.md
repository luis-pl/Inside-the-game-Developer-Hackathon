# Inside the game: Developer Hackathon

Demo de datos publicada en Azure: [API y Swagger](https://api-inside-game.redhill-f7b17d2a.canadacentral.azurecontainerapps.io/docs). MCP remoto: `https://api-inside-game.redhill-f7b17d2a.canadacentral.azurecontainerapps.io/mcp`. Las consultas requieren una credencial individual de equipo o agente. [Acceso y operación en Azure](docs/azure-demo.md).

La API de analítica deportiva está implementada: **25 consultas predeterminadas y nueve análisis espaciales/topológicos**, conectados a Azure SQL mediante lectura. Inicio local en Windows: `scripts/start-api.ps1`; documentación interactiva: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

El [visor de partidos](docs/topology-lab.md) usa por defecto **diez partidos reales**:
dos anonimizados de [Metrica Sports](https://github.com/metrica-sports/sample-data)
y ocho seudonimizados de [SkillCorner](https://github.com/SkillCorner/opendata),
con eventos y tracking sincronizados a 5 Hz. Cinco minutos se reproducen en
300 segundos a 1×. Arranque: `scripts/start-dashboard.ps1`. Se conservan los
datos sintéticos como historial separado. [Procedencia, verificación y límites](database/azure-sql/DATA-QUALITY.md).

El servidor MCP también está implementado: expone las mismas 34 operaciones por `stdio` o HTTP local en `http://127.0.0.1:8001/mcp`, a través de la API. Inicio HTTP: `scripts/start-mcp.ps1 -Transport streamable-http`.

El [agente de datos](docs/data-agent.md) recibe texto y contexto opcional, selecciona consultas MCP y devuelve evidencia original. Incluye prompt editable, proveedores Responses/Chat Completions y CLI `inside-game-data-agent`. El modelo local seleccionado es **Beam Free mediante OpenCode Go**, autenticado con la sesión autorizada del CLI. Estado en [agent-model.json](deployment/agent-model.json).

DeepSeek V4 Flash está desplegado como candidato: pasó una consulta real de tiros con un catálogo reducido, pero las dos pruebas con las 34 herramientas terminaron parciales por cuota de 20.000 TPM. No se activó como modelo predeterminado. [Resultados y límites](docs/deepseek-v4.md).

La conexión [OpenCode Go con Beam Free](docs/opencode.md) verificó catálogo, precios publicados cero y una consulta real modelo → MCP → SQL. Se mantiene `INSIDE_GAME_OPENCODE_FREE_ONLY=1`: si no se confirma precio cero, se detiene antes de inferencia. No se compraron créditos ni se activó fallback a Console/Zen. La [demostración trazada](docs/examples/agent-live-demo-20261024/README.md) conserva entrada, llamadas y evidencia; una prueba acotada no equivale al QA de todo el corpus. Los ensayos con Luna/GPT-OSS/DeepSeek quedan como historial. El [presupuesto Azure](deployment/demo-budget.json) sólo registra un objetivo y no corta consumo.

Instalación, ejemplos y límites: [API](docs/api.md) y [MCP](docs/mcp.md). Verificación contra Azure: [API](docs/api-verification.json), [MCP stdio](docs/mcp-verification-stdio.json), [MCP HTTP](docs/mcp-verification-streamable-http.json) y [datos reales](docs/metrica-service-verification.json). El intérprete, analista, dashboard builder y comunicación A2A siguen pendientes.

El frontend [Topology Lab](docs/topology-lab.md) está implementado con reproducción a tiempo real, persistencia, conectividad y descomposición de Hodge de la red de pases. Es un visor determinista y no requiere el LLM para mostrar los partidos.

> Build something that breaks the fourth wall.

**Inside the game** is a developer hackathon where participants build tools, games,
plugins, and experiments that live *inside* the world of software — the ones that
sit between the developer's intent and the machine's behavior.

🔒 **Private repository** — invitation only.

---

## 🎯 The premise

Most software is a black box: you type a request, you get a response. `Inside the game`
asks you to open the box. Build the thing that makes the invisible visible, the
boring fascinating, and the friction disappear.

### Track ideas

| Track | Description | Starter ideas |
| --- | --- | --- |
| **Tooling** | Developer tools that make other developer tools better | Live-reload inspector, diff-aware code review bot |
| **Visualization** | Making hidden state visible | Profiler overlay, state inspector, dependency graph explorer |
| **Play** | Games and playful interfaces | Gamified TODOs, typing-speed trainer, code golf |
| **Meta** | Tools about tools | A tool that builds tools, repo archaeology, prompt linter |

## 🏆 Rules

1. **48 hours**, starting at the kickoff.
2. **Teams of 2–4.** Solo entries are welcome and encouraged for first-timers.
3. **Ship a working demo** — a deployable URL, a video, or a binary. Slides alone don't win.
4. **Original work.** Forking an existing OSS project is fine; *credit it* and build something new on top.
5. **Use AI freely**, but the code must run without a paid API key.

## 🧰 Stack

Bring your own stack. Recommended defaults:

- **Frontend:** TypeScript, React, Vite, Tailwind
- **Backend:** Node.js, Bun, or Python (FastAPI)
- **Local-first:** SQLite / JSON on disk beats a hosted DB for a 48h build
- **Hosting:** Vercel, Cloudflare Pages, Fly.io, Fly.io — free tiers are fine

## 🏗️ Project structure

```
.
├── README.md        # You are here
├── .gitignore       # Keep build artifacts out
├── src/inside_game/ # Python backend scaffold
├── frontend/        # React/TypeScript topology dashboard
├── prompts/         # Agent prompts, pending implementation
├── tests/           # Tests, pending implementation
├── docs/            # Repository documentation
├── database/        # Existing Azure SQL schema and synthetic data tools
├── drafts/          # Design references
├── AGENTS.md        # Repository guidance
└── pyproject.toml   # Python package metadata
```

The initial scaffold is documented in [docs/repository-structure.md](docs/repository-structure.md).
The API, analytics service, SQL tools and MCP adapter are implemented. Agent modules remain placeholders. The Topology Lab frontend is implemented.

## 📋 Submission checklist

- [ ] `README.md` explains what it does and how to run it
- [ ] One command to run it locally (`npm run dev`, `uv run dev`, etc.)
- [ ] A short demo video or GIF
- [ ] A one-paragraph pitch: what it does, who it's for, why it's fun

## 👥 Team

| Name | Role | GitHub |
| --- | --- | --- |
| _add yourself_ | | |

## 📅 Schedule

| Time (UTC) | Event |
| --- | --- |
| Fri 18:00 | Kickoff & team formation |
| Fri 21:00 | Idea pitch round (2 min each) |
| Sat 09:00 | Midpoint check-in |
| Sat 18:00 | Freeze: no new features after this |
| Sun 14:00 | Demos (5 min each) |
| Sun 16:00 | Winners & awards |

---

*Built with curiosity. Enter the game.*

## Topology Lab

Dashboard de cancha con tracking, conectividad H0/H1, espacio libre y retirada de nodos. Inicio local: .\scripts\start-dashboard.ps1. Consulta docs/topology-lab.md para credenciales, arquitectura y definiciones matemáticas.
