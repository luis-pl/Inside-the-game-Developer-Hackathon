"""Protocolo del planificador con un modelo guionizado: sin red ni inferencia."""

import asyncio
import itertools
import json

from inside_game.agents.insights_agent.planner import Planner, PlannerLimits
from inside_game.providers.models import ModelTurn

MATCH = {
    "match_id": 900001,
    "home_team_id": 1,
    "home_team_name": "Synthetic FC 1",
    "away_team_id": 2,
    "away_team_name": "Synthetic FC 2",
    "home_score": 1,
    "away_score": 2,
    "match_date": "2026-10-01",
    "competition_name": "Synthetic Demo League",
    "is_synthetic": True,
    "provider": None,
}
LINEUPS = [
    {
        "team_id": 1,
        "player_id": 110,
        "jersey_number": 10,
        "player_name": "Synthetic Player 1-10",
    },
    {
        "team_id": 2,
        "player_id": 210,
        "jersey_number": 10,
        "player_name": "Synthetic Player 2-10",
    },
]


def page(data):
    return {"response": {"data": data}}


class FakeData:
    def __init__(self):
        self.calls = []

    async def fetch(self, operation, arguments):
        self.calls.append(operation)
        if operation == "list_matches":
            return [page({"items": [MATCH]})], None
        if operation == "get_match_context" and arguments["match_id"] == 900001:
            return [
                page({"match": MATCH, "lineups": LINEUPS, "position_intervals": []})
            ], None
        return [], "NOT_FOUND"


CALL_IDS = itertools.count(1)


def call(name, arguments):
    return {
        "type": "function_call",
        "call_id": f"c{next(CALL_IDS)}",
        "name": name,
        "arguments": json.dumps(arguments),
    }


class ScriptedModel:
    """Devuelve los turnos indicados y guarda lo que recibió en cada uno."""

    name = "scripted"

    def __init__(self, *turns):
        self.turns = list(turns)
        self.seen = []

    async def respond(self, instructions, messages, tools):
        self.seen.append([dict(m) for m in messages])
        output = self.turns.pop(0)
        return ModelTurn(output if isinstance(output, list) else [output], 10)


def plan(model, question="Resumen del partido", **kwargs):
    profiles = {"synthetic": {"unavailable": {"xg_story": "Sin xG."}, "zero_only": {}}}
    planner = Planner(model, FakeData(), profiles=profiles, prompt="prompt", **kwargs)
    return asyncio.run(planner.plan(question)), model


def outputs(model, turn):
    return [
        json.loads(m["output"])
        for m in model.seen[turn]
        if m.get("type") == "function_call_output"
    ]


def test_resolves_ids_with_tools_and_returns_validated_intent():
    result, model = plan(
        ScriptedModel(
            call("list_matches", {}),
            call("get_match_roster", {"match_id": 900001}),
            call(
                "submit_intent",
                {"template_id": "player_dossier", "match_id": 900001, "player_id": 110},
            ),
        ),
        "Ficha del número 10 del Synthetic FC 1",
    )
    assert result.status == "intent"
    assert result.intent.player_id == 110 and result.model_turns == 3
    matches = outputs(model, 1)[0]["matches"]
    assert matches[0]["home"] == {"team_id": 1, "name": "Synthetic FC 1"}
    roster = outputs(model, 2)[1]
    assert {"player_id": 110, "jersey_number": 10}.items() <= roster["players"][
        0
    ].items()
    assert roster["not_available"] == ["xg_story"]


def test_first_message_carries_request_id_for_the_go_session():
    result, model = plan(
        ScriptedModel(call("decline_request", {"reason": "Fuera de alcance."}))
    )
    first = json.loads(model.seen[0][0]["content"])
    assert first["request_id"] == str(result.request_id)
    assert first["question"] == "Resumen del partido"


def test_invented_ids_go_back_to_the_model_until_corrected():
    result, model = plan(
        ScriptedModel(
            call(
                "submit_intent",
                {"template_id": "match_overview", "match_id": 900001, "team_id": 99},
            ),
            call(
                "submit_intent",
                {"template_id": "player_dossier", "match_id": 900001, "player_id": 999},
            ),
            call(
                "submit_intent", {"template_id": "match_overview", "match_id": 900404}
            ),
            call(
                "submit_intent",
                {"template_id": "match_overview", "match_id": 900001, "team_id": 2},
            ),
        )
    )
    assert result.status == "intent" and result.intent.team_id == 2
    errors = [outputs(model, t)[-1]["error"]["code"] for t in (1, 2, 3)]
    assert errors == ["TEAM_NOT_IN_MATCH", "PLAYER_NOT_IN_MATCH", "MATCH_NOT_FOUND"]


def test_contract_errors_are_reported_by_field():
    result, model = plan(
        ScriptedModel(
            call(
                "submit_intent", {"template_id": "player_dossier", "match_id": 900001}
            ),
            call(
                "submit_intent", {"template_id": "match_overview", "match_id": 900001}
            ),
        )
    )
    assert result.status == "intent"
    assert outputs(model, 1)[0]["error"]["code"] == "INVALID_ARGUMENT"


def test_clarification_and_decline_are_final_states():
    clarified, _ = plan(
        ScriptedModel(
            call(
                "ask_clarification",
                {"question": "¿Qué partido?", "options": ["900001", "900003"]},
            )
        )
    )
    assert clarified.status == "clarification" and clarified.options == [
        "900001",
        "900003",
    ]
    declined, _ = plan(
        ScriptedModel(call("decline_request", {"reason": "Es una predicción."}))
    )
    assert declined.status == "declined" and declined.message == "Es una predicción."


def test_finish_mixed_with_other_calls_is_rejected():
    result, model = plan(
        ScriptedModel(
            [
                call("list_matches", {}),
                call(
                    "submit_intent",
                    {"template_id": "match_overview", "match_id": 900001},
                ),
            ],
            call(
                "submit_intent", {"template_id": "match_overview", "match_id": 900001}
            ),
        )
    )
    assert result.status == "intent"
    assert {o["error"]["code"] for o in outputs(model, 1)} == {
        "FINISH_MUST_BE_SEPARATE"
    }


def test_text_only_replies_and_turn_budget_end_in_errors():
    text = {
        "type": "chat_message",
        "message": {"role": "assistant", "content": "El partido fue..."},
    }
    talked, _ = plan(ScriptedModel(text, text, text))
    assert talked.status == "error" and talked.issues == ["MODEL_EXPECTED_TOOL_CALL"]
    looping, _ = plan(
        ScriptedModel(*[call("list_matches", {}) for _ in range(3)]),
        limits=PlannerLimits(max_turns=3),
    )
    assert looping.status == "error" and looping.issues == ["TURN_BUDGET_EXCEEDED"]


def test_follow_up_receives_the_previous_intent():
    previous = {"template_id": "match_overview", "match_id": 900001}
    result, model = plan(
        ScriptedModel(call("submit_intent", {**previous, "period": 2})),
        {"question": "¿Y el segundo tiempo?", "previous_intent": previous},
    )
    assert (
        json.loads(model.seen[0][0]["content"])["previous_intent"]["match_id"] == 900001
    )
    assert result.intent.period == 2
