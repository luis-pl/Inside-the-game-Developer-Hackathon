# Inside the game: Developer Hackathon

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
├── frontend/        # Frontend scaffold
├── prompts/         # Agent prompts, pending implementation
├── tests/           # Tests, pending implementation
├── docs/            # Repository documentation
├── database/        # Existing Azure SQL schema and synthetic data tools
├── drafts/          # Design references
├── AGENTS.md        # Repository guidance
└── pyproject.toml   # Python package metadata
```

The initial scaffold is documented in [docs/repository-structure.md](docs/repository-structure.md).
The new backend modules are placeholders; their application logic is pending implementation.

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
