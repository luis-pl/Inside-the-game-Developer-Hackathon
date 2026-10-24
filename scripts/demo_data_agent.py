"""Run a named-match demo with visible tool calls and original MCP output."""

import argparse
import asyncio
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from inside_game.agents.contracts import DataRequest
from inside_game.agents.data_agent import AgentLimits, DataAgent, load_prompt
from inside_game.providers.models import create_model
from inside_game.tools.mcp_client import DataMcpSettings, connect_data_mcp


def save(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


class Trace:
    def __init__(self, folder):
        self.folder, self.started, self.events = folder, time.monotonic(), []

    def record(self, kind, **fields):
        event = {
            "step": len(self.events) + 1,
            "elapsed_seconds": round(time.monotonic() - self.started, 3),
            "kind": kind,
            **fields,
        }
        self.events.append(event)
        with (self.folder / "trace.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        public = {k: v for k, v in event.items() if k not in {"response"}}
        print(json.dumps(public, ensure_ascii=False), flush=True)


class VisibleModel:
    def __init__(self, model, trace):
        self.model, self.trace, self.name = model, trace, model.name

    async def respond(self, instructions, messages, tools):
        self.trace.record("model_started", model=self.name)
        result = await self.model.respond(instructions, messages, tools)
        # Record executable proposals only; never expose model reasoning content.
        calls = [item for item in result.output if item.get("type") == "function_call"]
        self.trace.record(
            "model_proposed_calls", calls=calls, total_tokens=result.total_tokens
        )
        return result


class VisibleMcp:
    def __init__(self, client, trace):
        self.client, self.trace = client, trace

    async def list_tools(self):
        result = await self.client.list_tools()
        save(
            self.trace.folder / "tools-catalog.json",
            [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in result.tools
            ],
        )
        self.trace.record("tools_discovered", count=len(result.tools))
        return result

    async def call_tool(self, name, arguments):
        self.trace.record("mcp_call", operation=name, arguments=arguments)
        result = await self.client.call_tool(name, arguments)
        response = result.structured_content
        self.trace.record(
            "mcp_result",
            operation=name,
            is_error=result.is_error,
            response=response,
            summary={
                "total": (response or {}).get("data", {}).get("total"),
                "is_synthetic": (response or {})
                .get("provenance", {})
                .get("is_synthetic"),
            },
        )
        return result


def write_review(folder, request, result, trace, prompt_hash):
    lines = [
        "# Demostración real del agente de datos",
        "",
        f"Modelo: `{result.model}`. Estado: **{result.status}**.",
        "",
        "## Entrada entregada al agente",
        "",
        request.request_text,
        "",
        "La entrada no incluye IDs ni consultas preseleccionadas. Los nombres y la fecha se tomaron del catálogo antes de esta ejecución.",
        "",
        "## Prompt utilizado",
        "",
        f"SHA-256: `{prompt_hash}`.",
        "",
        "[Copia exacta del prompt](prompt-used.md) · [Entrada JSON](input.json) · [Catálogo de herramientas](tools-catalog.json)",
        "",
        "## Secuencia observada",
        "",
    ]
    for event in trace.events:
        if event["kind"] == "mcp_call":
            lines += [
                f"### {event['step']}. {event['operation']} · {event['elapsed_seconds']} s",
                "",
                "```json",
                json.dumps(event["arguments"], ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        elif event["kind"] == "mcp_result":
            lines += [
                f"Respuesta MCP: {'error' if event['is_error'] else 'correcta'}. [Datos completos en la traza](trace.jsonl).",
                "",
            ]
        elif event["kind"] == "model_proposed_calls":
            for call in event["calls"]:
                if call.get("name") == "finish_data_request":
                    lines += [
                        "### Finalización propuesta por el modelo",
                        "",
                        "```json",
                        json.dumps(
                            json.loads(call["arguments"]), ensure_ascii=False, indent=2
                        ),
                        "```",
                        "",
                    ]
    lines += [
        "## Salida original",
        "",
        "[Output completo del agente, con evidencia MCP sin reemplazar cifras](output.json)",
        "",
    ]
    for evidence in result.evidence:
        data = evidence.response.data
        lines += [
            f"### {evidence.evidence_id}: {evidence.operation}",
            "",
            "```json",
            json.dumps(
                {k: v for k, v in data.items() if k in {"total", "summary", "match"}},
                ensure_ascii=False,
                indent=2,
            ),
            "```",
            "",
        ]
        if evidence.operation == "get_shots":
            lines += [
                "| Evento | Período | Reloj del período | X | Y | Resultado |",
                "|---|---:|---|---:|---:|---|",
            ]
            for e in data.get("items", []):
                lines.append(
                    f"| {e.get('event_id')} | {e.get('period')} | {e.get('timestamp')} | {e.get('location_x')} | {e.get('location_y')} | {(e.get('shot') or {}).get('outcome')} |"
                )
            lines += [
                "",
                "Coordenadas de eventos 120×80, relativas al equipo actuante; conservar la procedencia sintética de este partido.",
                "",
            ]
    lines += [
        "## Alcance de la ejecución",
        "",
        f"{result.model_turns} turnos del modelo; {result.tool_calls} llamadas MCP; {result.total_tokens} tokens reportados.",
        "",
        "El agente propone llamadas MCP parametrizadas. El servidor ejecuta consultas y cálculos predefinidos; no se genera SQL libre. Esta traza muestra acciones y resultados observables, sin razonamiento interno ni credenciales.",
        "",
    ]
    (folder / "README.md").write_text("\n".join(lines), encoding="utf-8")


async def main(args):
    args.output_dir.mkdir(parents=True, exist_ok=False)
    prompt = load_prompt()
    (args.output_dir / "prompt-used.md").write_text(prompt, encoding="utf-8", newline="\n")
    digest = hashlib.sha256(prompt.encode()).hexdigest()
    trace = Trace(args.output_dir)
    async with connect_data_mcp(DataMcpSettings.from_env()) as mcp:
        catalogue = await mcp.call_tool("list_matches", {"limit": 100})
        if catalogue.is_error:
            raise RuntimeError("Catalogue unavailable")
        save(
            args.output_dir / "catalogue-preparation.json", catalogue.structured_content
        )
        match = next(
            x
            for x in catalogue.structured_content["data"]["items"]
            if x["match_id"] == args.match_id
        )
        text = args.text or (
            f"En el partido {match['home_team_name']} contra {match['away_team_name']} del {match['match_date']}, "
            "obtén el contexto del partido y todos los tiros a puerta del equipo local, "
            "con su resumen, momento y coordenadas. Resuelve el partido por sus nombres y fecha; "
            "entrega la evidencia original sin realizar análisis deportivo."
        )
        request = DataRequest(request_text=text)
        save(args.output_dir / "input.json", request.model_dump(mode="json"))
        trace.record(
            "request",
            request_text=text,
            prompt_sha256=digest,
            started_at_utc=datetime.now(UTC).isoformat(),
        )
        async with create_model() as model:
            agent = DataAgent(
                VisibleModel(model, trace),
                prompt=prompt,
                limits=AgentLimits(max_tokens=160000, timeout_seconds=360),
            )
            result = await agent.run(request, VisibleMcp(mcp, trace))
        save(args.output_dir / "output.json", result.model_dump(mode="json"))
        write_review(args.output_dir, request, result, trace, digest)
        trace.record(
            "finished",
            status=result.status,
            tool_calls=result.tool_calls,
            model_turns=result.model_turns,
            issues=[i.model_dump() for i in result.issues],
        )
        return result.status


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--match-id", type=int, default=900001)
    parser.add_argument("--text")
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    # Same assignments as the launcher; no evaluation and no credential copying.
    env_file = Path(__file__).resolve().parents[1] / ".env.local"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip().startswith("INSIDE_GAME_"):
                os.environ.setdefault(name.strip(), value.strip().strip("\"'"))
    try:
        status = asyncio.run(main(arguments))
    except Exception:  # noqa: BLE001 - CLI boundary must not expose SDK credentials.
        parser.exit(
            1,
            "Demo could not start; check model/MCP configuration. No credentials were logged.\n",
        )
    raise SystemExit(0 if status == "complete" else 3)
