"""InsightsAgent.ask(): de punta a punta sin red; modelo guionizado cuando hace falta."""

import asyncio
import copy
import itertools
import json
import re

from inside_game.agents.insights_agent.agent import InsightsAgent, resolver_error
from inside_game.agents.insights_agent.composer import stable_metrics
from inside_game.insights.demo import demo_manifest
from inside_game.providers.models import ModelTurn
from inside_game.tools.evidence_client import EvidenceClient

FIXTURE = {e["operation"]: e["response"] for e in demo_manifest()["evidence"]}
CONTEXT = {
    "match": {
        "match_id": 900001,
        "home_team_id": 1,
        "home_team_name": "Synthetic FC 1",
        "away_team_id": 2,
        "away_team_name": "Synthetic FC 2",
        "competition_name": "Synthetic Demo League",
        "is_synthetic": True,
        "provider": None,
        "data_kind": None,
    },
    "lineups": [
        {"team_id": 1, "player_id": 110, "player_name": "Synthetic Player 1-10"}
    ],
    "position_intervals": [],
    "periods": [{"period": 1, "home_attacks_positive_x": True, "duration_ms": 2700000}],
}
SHOTS_AND_PASSES = {
    "template_id": "custom_report",
    "match_id": 900001,
    "insight_ids": ["shot_map", "pass_map"],
}


class FakeApi:
    def __init__(self, errors=None):
        self.errors = errors or {}
        self.calls = []

    async def call(self, operation, arguments):
        self.calls.append(operation)
        if operation in self.errors:
            return None, self.errors[operation]
        response = copy.deepcopy(FIXTURE[operation])
        if operation == "get_match_context":
            response["data"] = copy.deepcopy(CONTEXT)
        return response, None


CALL_IDS = itertools.count(1)


def call(name, arguments):
    return {
        "type": "function_call",
        "call_id": f"c{next(CALL_IDS)}",
        "name": name,
        "arguments": json.dumps(arguments),
    }


class ScriptedModel:
    name = "scripted"

    def __init__(self, *turns):
        self.turns = list(turns)
        self.first_messages = []

    async def respond(self, instructions, messages, tools):
        self.first_messages.append(json.loads(messages[0]["content"]))
        return ModelTurn([self.turns.pop(0)], 10)


def ask(request, *, model=None, api=None):
    api = api or FakeApi()
    agent = InsightsAgent(EvidenceClient(api), model=model, profiles={})
    return asyncio.run(agent.ask(request)), api


def test_intent_produces_a_report_with_stable_metrics_and_next_state():
    result, _ = ask({"intent": SHOTS_AND_PASSES})
    answer = result.answer
    assert answer.kind == "report" and answer.has_report
    assert "<svg" in result.report_html
    # Los gráficos nombran a los equipos (contexto del partido), no "Equipo 1".
    assert "Equipo 1" not in result.report_html
    assert "Synthetic FC 1" in result.report_html
    assert answer.labels.synthetic and "SINTÉTICO" in answer.summary
    assert [b.insight_id for b in answer.blocks] == ["shot_map", "pass_map"]
    # Sin IDs de consulta: la misma métrica se llama igual en cualquier transporte.
    keys = [k for b in answer.blocks for k in b.metrics]
    assert keys and not any(re.match(r"^q\d+\.", k) for k in keys)
    assert answer.next.intent == answer.intent
    assert set(answer.timings_ms) >= {"resolve_ms", "compose_ms", "total_ms"}
    # La respuesta es pequeña: el HTML viaja aparte.
    assert len(answer.model_dump_json()) < len(result.report_html) / 10


def test_player_dossier_normalizes_a_conflicting_team_and_explains_it():
    result, _ = ask(
        {
            "intent": {
                "template_id": "player_dossier",
                "match_id": 900001,
                "player_id": 110,
                "team_id": 2,
            }
        }
    )
    answer = result.answer
    assert answer.kind == "report"
    assert answer.intent.team_id == 1
    assert "Equipo protagonista ajustado" in answer.summary
    assert "no a Synthetic FC 2" in answer.summary


def test_text_without_model_says_so_and_keeps_the_conversation():
    previous = {"intent": SHOTS_AND_PASSES}
    result, api = ask({"question": "¿Y el segundo tiempo?", "previous": previous})
    assert result.answer.kind == "error" and result.answer.issues == [
        "MODEL_UNAVAILABLE"
    ]
    assert result.answer.next.intent.match_id == 900001
    assert api.calls == []


def test_clarification_round_trip_reaches_the_planner_and_resolves():
    model = ScriptedModel(
        call(
            "ask_clarification",
            {"question": "¿Qué partido?", "options": ["900001", "900003"]},
        )
    )
    first, api = ask({"question": "El partido del Synthetic FC 1"}, model=model)
    assert first.answer.kind == "clarification" and api.calls == []
    assert first.answer.next.question == "El partido del Synthetic FC 1"

    model = ScriptedModel(call("submit_intent", SHOTS_AND_PASSES))
    second, _ = ask(
        {"question": "el primero", "previous": first.answer.next.model_dump()},
        model=model,
    )
    sent = model.first_messages[0]
    assert sent["clarified_question"] == "El partido del Synthetic FC 1"
    assert sent["clarification"]["options"] == ["900001", "900003"]
    assert second.answer.kind == "report" and second.answer.intent.match_id == 900001


def test_declined_questions_do_not_touch_the_data():
    model = ScriptedModel(call("decline_request", {"reason": "Es una predicción."}))
    result, api = ask({"question": "¿Quién ganará el Mundial?"}, model=model)
    assert (
        result.answer.kind == "declined"
        and result.answer.summary == "Es una predicción."
    )
    assert api.calls == [] and result.report_html is None


def test_data_agent_failure_becomes_a_coded_error_with_its_cause():
    down, _ = ask(
        {"intent": SHOTS_AND_PASSES},
        api=FakeApi(errors={"get_match_context": "API_UNAVAILABLE"}),
    )
    assert down.answer.kind == "error"
    assert down.answer.issues == ["MATCH_CONTEXT_UNAVAILABLE", "API_UNAVAILABLE"]
    missing, _ = ask(
        {"intent": SHOTS_AND_PASSES},
        api=FakeApi(errors={"get_match_context": "NOT_FOUND"}),
    )
    assert missing.answer.issues == ["MATCH_NOT_FOUND"]
    assert missing.answer.summary == "Ese partido no está en el catálogo."


def test_resolver_messages_never_leak_as_codes():
    from pydantic import BaseModel, ValidationError

    class Strict(BaseModel):
        n: int

    try:
        Strict(n="x")
    except ValidationError as exc:
        leaked = exc
    assert resolver_error(leaked) == ("RESOLVE_FAILED", None)
    assert resolver_error(ValueError("TEAM_NOT_IN_MATCH")) == (
        "TEAM_NOT_IN_MATCH",
        None,
    )
    assert resolver_error(ValueError("MATCH_CONTEXT_UNAVAILABLE: free text here")) == (
        "MATCH_CONTEXT_UNAVAILABLE",
        None,
    )


def test_model_failures_are_explained_as_model_failures():
    class BrokenModel:
        name = "broken"

        async def respond(self, *args):
            from inside_game.providers.models import ModelFailure

            raise ModelFailure("MODEL_AUTHENTICATION_FAILED")

    result, api = ask({"question": "Resumen del 900001"}, model=BrokenModel())
    assert result.answer.issues == ["MODEL_AUTHENTICATION_FAILED"]
    assert "modelo" in result.answer.summary and api.calls == []


def test_invalid_requests_are_answered_not_raised():
    for request in (
        {"question": "hola", "intent": SHOTS_AND_PASSES},
        {"question": "   "},
    ):
        result, _ = ask(request)
        assert result.answer.kind == "error" and result.answer.issues == [
            "INVALID_REQUEST"
        ]


def test_stable_metrics_strip_query_ids_and_disambiguate_collisions():
    evidence = [
        {"query_id": "a1-q3", "operation": "get_shots"},
        {"query_id": "a1-q4", "operation": "get_metric_series"},
    ]
    metrics = {"a1-q3.shots": 5, "a1-q3.total": 9, "a1-q4.total": 7, "density": 0.4}
    assert stable_metrics(metrics, evidence) == {
        "shots": 5,
        "get_shots.total": 9,
        "get_metric_series.total": 7,
        "density": 0.4,
    }
    # Dos consultas de la misma operación: no se pierde ninguna métrica.
    same = [
        {"query_id": "a1-q1", "operation": "get_passes"},
        {"query_id": "a1-q2", "operation": "get_passes"},
    ]
    stable = stable_metrics({"a1-q1.total": 3, "a1-q2.total": 4}, same)
    assert sorted(stable.values()) == [3, 4]
