"""HTTP local de QA con trazabilidad explícita de prompts y tools (sin secretos).

Sólo registra entradas, llamadas de herramientas y respuestas de herramientas.
No exporta bloques de razonamiento interno ni credenciales del proveedor.
Usar con las solicitudes de demostración de qa_insight_agent.py.
"""

import argparse
import hashlib
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import uvicorn

from inside_game.agents.data_agent import load_prompt as data_prompt
from inside_game.agents.page_builder import load_prompt as insights_prompt
from inside_game.agents_cli import app_from_env, load_local_env
from inside_game.providers.models import create_model
from inside_game.tools.mcp_client import DataMcpSettings


def visible_messages(messages):
    # Los ítems reasoning del SDK se reenvían al proveedor durante la ejecución,
    # pero no pertenecen a esta bitácora exportable.
    return [
        m
        for m in messages
        if m.get("role") == "user"
        or m.get("type") in {"function_call", "function_call_output"}
    ]


def tracing_factory(folder, forbidden_secret):
    prompts = {"data": data_prompt(), "insights": insights_prompt()}
    for agent, prompt in prompts.items():
        (folder / f"prompt-{agent}.md").write_bytes(prompt.encode("utf-8"))

    class TracedModel:
        def __init__(self, model):
            self.model, self.name = model, model.name

        async def respond(self, instructions, messages, tools):
            agent = next(
                (name for name, prompt in prompts.items() if prompt == instructions),
                "unknown",
            )
            record = {
                "agent": agent,
                "model": self.name,
                "started_utc": datetime.now(UTC).isoformat(),
                "prompt_sha256": hashlib.sha256(instructions.encode()).hexdigest(),
                "messages": visible_messages(messages),
            }
            (folder / f"tools-{agent}.json").write_text(
                json.dumps(tools, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            started = perf_counter()
            try:
                turn = await self.model.respond(instructions, messages, tools)
                record.update(
                    tool_calls=[
                        c for c in turn.output if c.get("type") == "function_call"
                    ],
                    total_tokens=turn.total_tokens,
                )
                return turn
            except BaseException:
                record["error"] = "MODEL_TURN_INTERRUPTED_OR_FAILED"
                raise
            finally:
                record["elapsed_ms"] = round((perf_counter() - started) * 1000, 3)
                encoded = json.dumps(record, ensure_ascii=False)
                if forbidden_secret and forbidden_secret in encoded:
                    raise ValueError("SECRET_IN_TRACE")
                with (folder / "llm-calls.jsonl").open("a", encoding="utf-8") as output:
                    output.write(encoded + "\n")

    @asynccontextmanager
    async def factory():
        async with create_model() as model:
            yield TracedModel(model)

    return factory


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8087)
    parser.add_argument(
        "--output-dir", type=Path, default=Path(".temp/insights/xg-review")
    )
    args = parser.parse_args()
    load_local_env(Path(__file__).resolve().parents[1])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    app = app_from_env(
        args.port,
        model_factory=tracing_factory(args.output_dir, DataMcpSettings.from_env().key),
    )
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)
