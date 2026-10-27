"""Intérprete de intención: delegaciones tipadas, nunca SQL, cifras o HTML."""

import hashlib
import json
import re
import sysconfig
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import Field, ValidationError

from inside_game.agents.contracts import DataContext, Message
from inside_game.agents.experiments import experiment
from inside_game.providers.models import ModelFailure


def team_ids_from(text, context, match_id, matches):
    """EXPERIMENTO LOCAL "guards": equipos del partido nombrados por el usuario.

    Sólo devuelve IDs que juegan ese partido según el catálogo: seleccionados,
    citados como "equipo N" o por su nombre completo.
    """
    row = next((m for m in matches if m.get("match_id") == match_id), None)
    if not row:
        return []
    names = {
        row.get("home_team_id"): row.get("home_team_name"),
        row.get("away_team_id"): row.get("away_team_name"),
    }
    names.pop(None, None)
    selected = [t for t in context.team_ids if t in names]
    if selected:
        return selected
    lowered = text.lower()
    found = [int(n) for n in re.findall(r"equipo\s+(\d+)", lowered) if int(n) in names]
    found += [t for t, name in names.items() if name and name.lower() in lowered]
    return list(dict.fromkeys(found))


class Interpretation(Message):
    action: Literal["create", "modify", "clarify", "catalog", "answer"]
    title: str = Field(min_length=1, max_length=100)
    reply: str = Field(min_length=1, max_length=1000)
    answer_topic: Literal["general", "welcome", "xg", "voronoi"] = "general"
    context: DataContext = Field(default_factory=DataContext)
    data_request: str = Field(default="", max_length=5000)
    analysis_request: str = Field(default="", max_length=5000)
    refresh_analysis: bool = True


def load_prompt():
    relative = "prompts/interpreter.md"
    local = Path(__file__).resolve().parents[3] / relative
    installed = Path(sysconfig.get_path("data")) / "share/inside-game" / relative
    return (local if local.is_file() else installed).read_text(encoding="utf-8")


class Interpreter:
    def __init__(self, model):
        self.model = model
        self.prompt = load_prompt()
        self.prompt_sha256 = hashlib.sha256(self.prompt.encode()).hexdigest()
        self.trace = []

    async def interpret(
        self, *, text, context, history, matches, report, request_id=None
    ):
        catalog = json.loads(
            (Path(__file__).resolve().parents[1] / "insights/catalog.json").read_text(
                encoding="utf-8"
            )
        )["insights"]
        messages = [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "request_id": str(request_id or uuid4()),
                        "request": text,
                        "selected_context": context.model_dump(mode="json"),
                        "history": history[-8:],
                        "available_matches": matches,
                        "current_report": report,
                        "insights": [
                            {k: i[k] for k in ("id", "title", "source_operations")}
                            for i in catalog
                        ],
                    },
                    ensure_ascii=False,
                ),
            }
        ]
        tools = [
            {
                "type": "function",
                "name": "delegate_request",
                "strict": False,
                "description": "Responde conceptos u orientación, o decide crear, modificar, mostrar partidos o pedir una aclaración. Sin SQL ni resultados deportivos inventados.",
                "parameters": Interpretation.model_json_schema(),
            }
        ]
        for _ in range(3):
            turn = await self.model.respond(self.prompt, messages, tools)
            calls = [c for c in turn.output if c.get("type") == "function_call"]
            messages.extend(turn.output)
            if not calls:
                messages.append(
                    {"role": "user", "content": "Responde llamando a delegate_request."}
                )
                continue
            call = calls[0]
            try:
                if call["name"] != "delegate_request" or len(call["arguments"]) > 18000:
                    raise ValueError("INVALID_DELEGATION")
                args = json.loads(call["arguments"])
                normalized = []
                if not isinstance(args, dict):
                    raise TypeError("OBJECT_REQUIRED")
                # Algunos tool callers serializan dos veces un campo. Sólo se
                # acepta JSON completo del tipo esperado; nunca se coercen IDs.
                for key, expected in {
                    "context": dict,
                    "action": str,
                    "title": str,
                    "reply": str,
                    "data_request": str,
                    "analysis_request": str,
                }.items():
                    value = args.get(key)
                    if isinstance(value, str) and value.lstrip().startswith(("{", '"')):
                        try:
                            decoded = json.loads(value)
                            if isinstance(decoded, expected):
                                args[key] = decoded
                                normalized.append(key)
                        except ValueError:
                            pass
                plan = Interpretation.model_validate(args)
                if (
                    experiment("guards")
                    and plan.action in {"create", "modify"}
                    and not plan.context.match_ids
                ):
                    # EXPERIMENTO LOCAL: el partido ya es conocido (selector o
                    # texto); el modelo a veces lo omite en el plan.
                    known = {m["match_id"] for m in matches}
                    selected = [m for m in context.match_ids if m in known]
                    named = [
                        int(m)
                        for m in re.findall(r"\b(9\d{5})\b", text)
                        if int(m) in known
                    ]
                    chosen = selected or list(dict.fromkeys(named))
                    if len(chosen) == 1:
                        plan.context.match_ids = chosen
                        normalized.append("context.match_ids")
                if (
                    experiment("guards")
                    and plan.action in {"create", "modify"}
                    and len(plan.context.match_ids) == 1
                    and not plan.context.team_ids
                ):
                    # EXPERIMENTO LOCAL: el equipo pedido (selector, "equipo N"
                    # o su nombre) no puede perderse; sin él, las cifras serían
                    # las del partido entero presentadas como del equipo.
                    teams = team_ids_from(
                        text, context, plan.context.match_ids[0], matches
                    )
                    if len(teams) == 1:
                        plan.context.team_ids = teams
                        normalized.append("context.team_ids")
                if plan.action == "clarify" and plan.reply.count("?") > 1:
                    raise ValueError("ASK_ONE_CLARIFYING_QUESTION")
                allowed = {m["match_id"] for m in matches}
                if not set(plan.context.match_ids) <= allowed:
                    raise ValueError("MATCH_NOT_IN_CATALOG")
                if plan.action in {"create", "modify"} and not plan.context.match_ids:
                    raise ValueError("MATCH_REQUIRED")
                if plan.action == "create" and not (
                    plan.data_request and plan.analysis_request
                ):
                    raise ValueError("DELEGATION_TEXT_REQUIRED")
                if plan.action == "modify" and not (report and plan.analysis_request):
                    raise ValueError("CURRENT_REPORT_REQUIRED")
                self.trace.append(
                    {
                        "tool": "delegate_request",
                        "status": "validated",
                        "normalized_fields": normalized,
                    }
                )
                return plan
            except (ValueError, ValidationError, KeyError, TypeError) as exc:
                code = (
                    {
                        "code": "INVALID_PLAN_FIELDS",
                        "fields": [
                            {"path": list(e["loc"]), "type": e["type"]}
                            for e in exc.errors()
                        ],
                    }
                    if isinstance(exc, ValidationError)
                    else {"code": str(exc)[:100]}
                )
                self.trace.append(
                    {"tool": "delegate_request", "status": "rejected", **code}
                )
                messages.append(
                    {
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": json.dumps({"error": code}),
                    }
                )
        raise ModelFailure("INTERPRETER_INVALID_PLAN")
