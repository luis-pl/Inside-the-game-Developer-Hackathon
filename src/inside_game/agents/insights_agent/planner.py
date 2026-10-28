"""Pregunta → InsightIntent. Única decisión de interpretación que toma el LLM.

El modelo dispone de dos herramientas de consulta (catálogo de partidos y
plantilla de un partido) y tres de cierre. El ejecutor valida cada intención
contra el contrato y contra los equipos y jugadores reales del partido: un ID
inventado vuelve al modelo como error, nunca llega al resolvedor.
"""

import asyncio
import hashlib
import json
import sysconfig
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import Field, ValidationError

from inside_game.agents.context_window import ContextWindow
from inside_game.agents.contracts import Message
from inside_game.contracts import Id
from inside_game.insights.catalog import RECIPES
from inside_game.language import Language
from inside_game.providers.models import ModelFailure, ModelProvider

from .contracts import Clarification, InsightIntent
from .profiles import load_profiles, source_key

SUBMIT, CLARIFY, DECLINE = "submit_intent", "ask_clarification", "decline_request"
FINISHERS = {SUBMIT, CLARIFY, DECLINE}


@dataclass(frozen=True)
class PlannerLimits:
    max_turns: int = 8
    max_tokens: int = 60000
    timeout_seconds: float = 40
    max_input_bytes: int = 180000


class InsightQuestion(Message):
    request_id: UUID = Field(default_factory=uuid4)
    language: Language = "es"
    question: Annotated[str, Field(min_length=1, max_length=2000)]
    previous_intent: InsightIntent | None = None
    # Aclaración que el agente pidió en el turno anterior y la pregunta que la originó.
    clarification: Clarification | None = None
    clarified_question: Annotated[str | None, Field(max_length=2000)] = None


class PlannerResult(Message):
    request_id: UUID
    status: Literal["intent", "clarification", "declined", "error"]
    intent: InsightIntent | None = None
    message: str | None = None
    options: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    model: str
    prompt_sha256: str
    model_turns: int = 0
    tool_calls: int = 0
    total_tokens: int = 0
    context_events: list[dict] = Field(default_factory=list)


class _Empty(Message):
    pass


class _Roster(Message):
    match_id: Id


class _Decline(Message):
    reason: Annotated[str, Field(min_length=1, max_length=500)]


TOOLS = {
    "list_matches": (
        _Empty,
        "Catálogo de partidos: IDs, equipos, fecha, marcador y fuente.",
    ),
    "get_match_roster": (
        _Roster,
        "Equipos, jugadores (nombre y dorsal) y recetas que la fuente del partido no puede mostrar.",
    ),
    SUBMIT: (InsightIntent, "Finaliza con la intención completa. Llamada separada."),
    CLARIFY: (
        Clarification,
        "Finaliza pidiendo una aclaración con opciones concretas.",
    ),
    DECLINE: (_Decline, "Finaliza: la pregunta no se puede responder con estos datos."),
}


def load_prompt():
    source = Path(__file__).resolve().parents[4] / "prompts/insights_planner.md"
    installed = (
        Path(sysconfig.get_path("data"))
        / "share/inside-game/prompts/insights_planner.md"
    )
    text = (source if source.is_file() else installed).read_text(encoding="utf-8")
    catalog = "\n".join(
        f"- `{key}`: {r['title']}. {r.get('question', '')}".rstrip()
        for key, r in RECIPES.items()
    )
    return text.rstrip() + "\n\n" + catalog + "\n"


class Planner:
    def __init__(
        self, model: ModelProvider, data, *, limits=None, prompt=None, profiles=None
    ):
        self.model = model
        self.data = data
        self.limits = limits or PlannerLimits()
        self.prompt = prompt if prompt is not None else load_prompt()
        self.profiles = load_profiles() if profiles is None else profiles

    async def plan(self, question: InsightQuestion | dict | str) -> PlannerResult:
        if isinstance(question, str):
            question = {"question": question}
        question = InsightQuestion.model_validate(question)
        run = _Run(self, question)
        try:
            async with asyncio.timeout(self.limits.timeout_seconds):
                return await run.execute()
        except TimeoutError:
            return run.result("error", issue="DEADLINE_EXCEEDED")
        except ModelFailure as exc:
            return run.result("error", issue=exc.code)
        except Exception:  # noqa: BLE001 - frontera pública; el detalle puede contener secretos.
            return run.result("error", issue="PLANNER_EXECUTION_FAILED")


class _Run:
    def __init__(self, planner, question):
        self.planner, self.question = planner, question
        self.turns = self.calls = self.tokens = 0
        self.issues = []
        self.context_window = ContextWindow(planner.limits.max_input_bytes)
        self.observations = {}

    def result(self, status, *, intent=None, message=None, options=(), issue=None):
        if issue:
            self.issues.append(issue)
        return PlannerResult(
            request_id=self.question.request_id,
            status=status,
            intent=intent,
            message=message,
            options=list(options),
            issues=self.issues,
            model=self.planner.model.name,
            prompt_sha256=hashlib.sha256(self.planner.prompt.encode()).hexdigest(),
            model_turns=self.turns,
            tool_calls=self.calls,
            total_tokens=self.tokens,
            context_events=self.context_window.events,
        )

    def checkpoint(self):
        return {
            **self.question.model_dump(mode="json"),
            "observed_tools": list(self.observations.values()),
        }

    async def execute(self):
        functions = [
            {
                "type": "function",
                "name": name,
                "description": description,
                "parameters": model.model_json_schema(),
                "strict": False,
            }
            for name, (model, description) in TOOLS.items()
        ]
        # La sesión Go exige un JSON con request_id en el primer mensaje del usuario.
        messages = [{"role": "user", "content": self.question.model_dump_json()}]
        # El catálogo de partidos llega ya consultado, como si el modelo lo hubiera
        # pedido: ahorra un turno de modelo en cada pregunta.
        try:
            catalog = await self.matches()
        except Exception:  # noqa: BLE001 - sin catálogo precargado el modelo lo pide.
            catalog = {"error": {"code": "PRELOAD_FAILED"}}
        if "error" not in catalog:
            self.observations["list_matches"] = {
                "operation": "list_matches",
                "arguments": {},
                "result": catalog,
            }
            call_id = "preloaded-list-matches"
            messages += [
                {
                    "type": "function_call",
                    "call_id": call_id,
                    "name": "list_matches",
                    "arguments": "{}",
                },
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(catalog, ensure_ascii=False),
                },
            ]
        text_only = 0
        while self.turns < self.planner.limits.max_turns:
            if self.tokens >= self.planner.limits.max_tokens:
                return self.result("error", issue="TOKEN_BUDGET_EXCEEDED")
            self.context_window.prepare(
                self.planner.model,
                self.planner.prompt,
                messages,
                functions,
                self.checkpoint,
            )
            turn = await self.planner.model.respond(
                self.planner.prompt, messages, functions
            )
            self.turns += 1
            self.context_window.observe(turn)
            self.tokens += turn.total_tokens
            messages.extend(turn.output)
            calls = [i for i in turn.output if i.get("type") == "function_call"]
            if not calls:
                if text_only >= 2:
                    return self.result("error", issue="MODEL_EXPECTED_TOOL_CALL")
                text_only += 1
                messages.append(
                    {
                        "role": "user",
                        "content": "No se aceptan respuestas en texto. Llama a una herramienta: "
                        "consulta list_matches/get_match_roster o finaliza con submit_intent, "
                        "ask_clarification o decline_request.",
                    }
                )
                continue
            separate = len(calls) == 1 or not any(
                c.get("name") in FINISHERS for c in calls
            )
            for call in calls:
                self.calls += 1
                if not separate:
                    output = {"error": {"code": "FINISH_MUST_BE_SEPARATE"}}
                else:
                    finished, output = await self.handle(call)
                    if finished is not None:
                        return finished
                messages.append(
                    {
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": json.dumps(output, ensure_ascii=False),
                    }
                )
        return self.result("error", issue="TURN_BUDGET_EXCEEDED")

    async def handle(self, call):
        name = call.get("name")
        if name not in TOOLS:
            return None, {"error": {"code": "UNKNOWN_TOOL"}}
        try:
            arguments = json.loads(call.get("arguments") or "{}")
            request = TOOLS[name][0].model_validate(arguments)
        except (ValueError, TypeError, ValidationError) as exc:
            fields = (
                [{"location": list(e["loc"]), "type": e["type"]} for e in exc.errors()]
                if isinstance(exc, ValidationError)
                else []
            )
            return None, {"error": {"code": "INVALID_ARGUMENT", "fields": fields}}
        if name == "list_matches":
            return None, await self.matches()
        if name == "get_match_roster":
            output = await self.roster(request.match_id)
            self.observations[f"roster:{request.match_id}"] = {
                "operation": name,
                "arguments": {"match_id": request.match_id},
                "result": output,
            }
            return None, output
        if name == CLARIFY:
            return self.result(
                "clarification", message=request.question, options=request.options
            ), None
        if name == DECLINE:
            return self.result("declined", message=request.reason), None
        error = await self.check(request)
        if error:
            return None, {"error": {"code": error}}
        request.language = self.question.language
        return self.result("intent", intent=request), None

    async def matches(self):
        pages, error = await self.planner.data.fetch("list_matches", {"limit": 100})
        if error:
            return {"error": {"code": error}}
        rows = [r for p in pages for r in p["response"]["data"]["items"]]
        return {
            "matches": [
                {
                    "match_id": r["match_id"],
                    "home": {"team_id": r["home_team_id"], "name": r["home_team_name"]},
                    "away": {"team_id": r["away_team_id"], "name": r["away_team_name"]},
                    "score": f"{r.get('home_score')}-{r.get('away_score')}",
                    "date": r.get("match_date")
                    if r.get("match_date_known", True)
                    else "desconocida",
                    "competition": r.get("competition_name"),
                    "source": source_key(r),
                }
                for r in rows
            ]
        }

    async def context(self, match_id):
        pages, error = await self.planner.data.fetch(
            "get_match_context", {"match_id": match_id}
        )
        if error or not pages:
            return None, error or "NOT_FOUND"
        return pages[0]["response"]["data"], None

    async def roster(self, match_id):
        context, error = await self.context(match_id)
        if error:
            return {"error": {"code": error}}
        match = context["match"]
        positions = {}
        for row in context.get("position_intervals", []):
            positions.setdefault(row["player_id"], row.get("position"))
        profile = self.planner.profiles.get(source_key(match), {})
        return {
            "match_id": match_id,
            "source": source_key(match),
            "teams": [
                {
                    "team_id": match["home_team_id"],
                    "name": match["home_team_name"],
                    "side": "local",
                },
                {
                    "team_id": match["away_team_id"],
                    "name": match["away_team_name"],
                    "side": "visitante",
                },
            ],
            "players": [
                {
                    "player_id": r["player_id"],
                    "name": r.get("player_nickname") or r.get("player_name"),
                    "jersey_number": r.get("jersey_number"),
                    "team_id": r["team_id"],
                    "position": positions.get(r["player_id"]),
                }
                for r in context.get("lineups", [])
            ],
            "not_available": sorted(
                set(profile.get("unavailable", {})) | set(profile.get("zero_only", {}))
            ),
        }

    async def check(self, intent):
        """IDs reales del partido; el modelo no puede colar un equipo o jugador ajeno."""
        context, error = await self.context(intent.match_id)
        if error:
            return "MATCH_NOT_FOUND" if error == "NOT_FOUND" else error
        match = context["match"]
        teams = {match["home_team_id"], match["away_team_id"]}
        players = {r["player_id"] for r in context.get("lineups", [])}
        if intent.team_id is not None and intent.team_id not in teams:
            return "TEAM_NOT_IN_MATCH"
        if intent.player_id is not None and intent.player_id not in players:
            return "PLAYER_NOT_IN_MATCH"
        valid = teams if intent.compare_kind == "team" else players
        if not set(intent.compare_ids) <= valid:
            return "COMPARE_ID_NOT_IN_MATCH"
        return None
