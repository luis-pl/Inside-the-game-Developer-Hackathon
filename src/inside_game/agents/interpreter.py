"""Intérprete de intención: delegaciones tipadas, nunca SQL, cifras o HTML."""

import hashlib
import json
import re
import sysconfig
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import Field, ValidationError

from inside_game.agents.context_window import ContextWindow
from inside_game.agents.contracts import DataContext, Message
from inside_game.agents.experiments import experiment, wants_both_teams
from inside_game.insights.catalog import InsightId
from inside_game.language import Language
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
    language: Language = "es"
    required_insights: list[InsightId] = Field(
        default_factory=list,
        max_length=40,
        description="Exact chart recipes requested for a new page, including duplicates only when separate charts were requested. One combined shot map for both teams is one shot_map, not two.",
    )
    action: Literal["create", "modify", "clarify", "catalog", "answer"]
    title: str = Field(min_length=1, max_length=100)
    reply: str = Field(min_length=1, max_length=1000)
    answer_topic: Literal["general", "welcome", "xg", "voronoi"] = "general"
    context: DataContext = Field(
        default_factory=DataContext,
        description="Only explicit changes to selected_context. Use {} to keep the selected match, team and temporal scope; IDs and times must be JSON integers.",
    )
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
        self.model_turns = self.total_tokens = 0
        self.context_window = ContextWindow(180000)

    async def interpret(
        self,
        *,
        text,
        context,
        history,
        matches,
        report,
        request_id=None,
        language=None,
        previous_language="es",
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
                        "language": language,
                        "previous_language": previous_language,
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
            self.context_window.prepare(
                self.model,
                self.prompt,
                messages,
                tools,
                lambda: json.loads(messages[0]["content"]),
            )
            turn = await self.model.respond(self.prompt, messages, tools)
            self.context_window.observe(turn)
            self.model_turns += 1
            self.total_tokens += turn.total_tokens
            calls = [c for c in turn.output if c.get("type") == "function_call"]
            messages.extend(turn.output)
            if not calls:
                messages.append(
                    {"role": "user", "content": "Responde llamando a delegate_request."}
                )
                continue
            call = calls[0]
            try:
                if len(calls) != 1:
                    raise ValueError("DELEGATE_MUST_BE_SEPARATE")
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
                    "required_insights": list,
                }.items():
                    value = args.get(key)
                    if isinstance(value, str) and value.lstrip().startswith(
                        ("{", "[", '"')
                    ):
                        try:
                            decoded = json.loads(value)
                            if isinstance(decoded, expected):
                                args[key] = decoded
                                normalized.append(key)
                        except ValueError:
                            pass
                raw_context = args.get("context")
                if isinstance(raw_context, dict) and raw_context.get(
                    "sample_step_ms"
                ) in {"200", "1000"}:
                    # Only the two finite sampling enums, never identities,
                    # timestamps or arbitrary numeric values, are normalized.
                    raw_context["sample_step_ms"] = int(raw_context["sample_step_ms"])
                    normalized.append("context.sample_step_ms")
                plan = Interpretation.model_validate(args)
                # Do not force the model to transcribe immutable selected IDs
                # and time windows. Omitted fields retain the typed selection;
                # explicit overrides must still pass the original strict types.
                plan.context = DataContext.model_validate(
                    {
                        **context.model_dump(mode="json"),
                        **plan.context.model_dump(mode="json", exclude_unset=True),
                    }
                )
                if language is not None:
                    plan.language = language
                # Una selección explícita e inequívoca no se pierde si el modelo
                # omite el partido. Nunca se elige una fila del catálogo al azar.
                if plan.action in {"create", "modify"} and not plan.context.match_ids:
                    selected = set(context.match_ids) & {m["match_id"] for m in matches}
                    if len(selected) == 1:
                        plan.context.match_ids = list(selected)
                        normalized.append("context.match_ids")
                if (
                    experiment("guards")
                    and plan.action in {"create", "modify"}
                    and not plan.context.match_ids
                ):
                    # EXPERIMENTO LOCAL: sin selección, el partido nombrado en el
                    # texto (un único ID del catálogo) no se pierde.
                    known = {m["match_id"] for m in matches}
                    named = [
                        int(m)
                        for m in re.findall(r"\b(9\d{5})\b", text)
                        if int(m) in known
                    ]
                    if len(set(named)) == 1:
                        plan.context.match_ids = [named[0]]
                        normalized.append("context.match_ids")
                if (
                    experiment("guards")
                    and plan.action in {"create", "modify"}
                    and len(plan.context.match_ids) == 1
                    and not plan.context.team_ids
                ):
                    # EXPERIMENTO LOCAL: el equipo pedido ("equipo N" o su nombre)
                    # no puede perderse; sin él, las cifras serían las del
                    # partido entero presentadas como del equipo.
                    teams = team_ids_from(
                        text, context, plan.context.match_ids[0], matches
                    )
                    if len(teams) == 1 and not wants_both_teams(text):
                        plan.context.team_ids = teams
                        normalized.append("context.team_ids")
                if (
                    experiment("guards")
                    and len(plan.context.team_ids) == 1
                    and wants_both_teams(text)
                ):
                    # EXPERIMENTO LOCAL: "ambos equipos" no se reduce al equipo
                    # nombrado; si no, sus cifras se presentan como de los dos.
                    plan.context.team_ids = []
                    normalized.append("context.team_ids")
                if plan.action == "clarify" and plan.reply.count("?") > 1:
                    raise ValueError("ASK_ONE_CLARIFYING_QUESTION")
                allowed = {m["match_id"] for m in matches}
                if not set(plan.context.match_ids) <= allowed:
                    raise ValueError("MATCH_NOT_IN_CATALOG")
                selected_rows = [
                    m for m in matches if m["match_id"] in plan.context.match_ids
                ]
                if selected_rows and all(
                    m.get("home_team_id") and m.get("away_team_id")
                    for m in selected_rows
                ):
                    teams = {
                        m[k]
                        for m in selected_rows
                        for k in ("home_team_id", "away_team_id")
                    }
                    if not set(plan.context.team_ids) <= teams:
                        raise ValueError("TEAM_NOT_IN_MATCH")
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
                if isinstance(exc, ValidationError):
                    code["repair"] = {
                        "context_to_reuse": context.model_dump(mode="json"),
                        "instruction": "Use context={} to retain this exact selected context. If overriding it, use flat scope={kind:window,period:1,start_ms:0,end_ms:20000} with JSON integers, never numeric strings or scope.window. Copy actual values from selected_context, not this structural example.",
                    }
                for rejected in calls:
                    messages.append(
                        {
                            "type": "function_call_output",
                            "call_id": rejected["call_id"],
                            "output": json.dumps({"error": code}),
                        }
                    )
        raise ModelFailure("INTERPRETER_INVALID_PLAN")
