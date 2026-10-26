"""CLI del agente de insights: una conversación de una o varias peticiones.

Cada `--intent` (JSON) o `--question` (texto) se envía en orden y la respuesta
`next` alimenta la siguiente, como haría la UI o el intérprete. Guarda cada
respuesta en JSON y su informe HTML aparte.

    python -m inside_game.agents.insights_agent --intent '{"template_id": "match_overview", "match_id": 900011}'
    python -m inside_game.agents.insights_agent --data-agent-url http://127.0.0.1:8010 --intent ... --question "¿y el segundo tiempo?"
    python -m inside_game.agents.insights_agent --insights-agent-url http://127.0.0.1:8020 --intent ...

Con --insights-agent-url la conversación va al agente de insights remoto por A2A
(y éste pide los datos al agente de datos). Si no, el agente corre aquí: con
--data-agent-url pide los datos por A2A; sin él, directamente a la API.
--question necesita el modelo configurado en el entorno (docs/opencode.md).
"""

import argparse
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from inside_game.local_env import local_setting

from .runtime import ROOT, load_settings, open_runtime


class Ordered(argparse.Action):
    """Conserva el orden mezclado de --intent y --question."""

    def __call__(self, parser, namespace, value, option_string=None):
        namespace.turns = [*getattr(namespace, "turns", []), (self.dest, value)]


@asynccontextmanager
async def open_agent(turns, data_agent_url, insights_agent_url):
    """Agente local o remoto; ambos exponen `ask()` y devuelven AskResult."""
    if insights_agent_url:
        from inside_game.a2a_agents.insights_client import connect_insights_agent

        token = local_setting("INSIDE_GAME_A2A_TOKEN", ROOT) or None
        async with connect_insights_agent(insights_agent_url, token=token) as agent:
            yield agent
        return
    use_model = any(kind == "question" for kind, _ in turns)
    async with open_runtime(data_agent_url=data_agent_url, use_model=use_model) as rt:
        # Un solo agente para toda la conversación: reutiliza su caché de datos.
        yield rt.new_agent()


async def converse(turns, folder, data_agent_url, insights_agent_url):
    async with open_agent(turns, data_agent_url, insights_agent_url) as agent:
        previous = None
        for n, (kind, value) in enumerate(turns, 1):
            request = {"previous": previous}
            request[kind] = json.loads(value) if kind == "intent" else value
            result = await agent.ask(request)
            answer = result.answer
            stem = folder / f"{n:02d}-{answer.kind}"
            stem.with_suffix(".json").write_text(
                answer.model_dump_json(indent=2), encoding="utf-8"
            )
            if result.report_html:
                stem.with_suffix(".html").write_text(
                    result.report_html, encoding="utf-8"
                )
            print(f"[{n}] {answer.kind} · {answer.timings_ms.get('total_ms')} ms")
            print(f"    {answer.summary}", flush=True)
            previous = answer.next.model_dump() if answer.next else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intent", action=Ordered, help="InsightIntent JSON")
    parser.add_argument("--question", action=Ordered, help="Pregunta en texto")
    parser.add_argument("--data-agent-url", help="URL A2A del agente de datos")
    parser.add_argument(
        "--insights-agent-url", help="URL A2A de un agente de insights remoto"
    )
    parser.add_argument("--output-dir", type=Path, default=Path(".temp/insights/agent"))
    args = parser.parse_args()
    load_settings()
    turns = getattr(args, "turns", [])
    if args.insights_agent_url and args.data_agent_url:
        # El agente remoto ya tiene su propio agente de datos; no se ignora en silencio.
        parser.error("--insights-agent-url y --data-agent-url son excluyentes")
    if not turns:
        parser.error("Indica al menos un --intent o --question")
    for kind, value in turns:
        if kind == "intent":
            try:
                json.loads(value)
            except ValueError:
                parser.error(f"--intent no es JSON válido: {value[:80]}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    asyncio.run(
        converse(turns, args.output_dir, args.data_agent_url, args.insights_agent_url)
    )


if __name__ == "__main__":
    main()
