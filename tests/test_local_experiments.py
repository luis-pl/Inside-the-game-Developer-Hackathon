"""EXPERIMENTO LOCAL: cambios activables con INSIDE_GAME_EXPERIMENTS."""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

from inside_game.agents.analyst_contracts import AnalysisRequest
from inside_game.agents.data_agent import tool_subset
from inside_game.agents.experiments import T, requested_visuals, wants_topology
from inside_game.agents.sports_analyst import SportsAnalyst, _Run
from inside_game.service import OPERATIONS
from tests.test_sports_analyst import RouterModel, evidence_result


class Insights:
    def __init__(self, blocks):
        self.blocks, self.calls = blocks, []

    async def preview(self, request, *, timeout):
        self.calls.append((request.request_text, timeout))
        return SimpleNamespace(
            status="complete", blocks=self.blocks, report_id=uuid4(), issues=[]
        ), None


def run_for(text, insights=None):
    analyst = SportsAnalyst(RouterModel(), insights_client=insights)
    return _Run(
        analyst,
        AnalysisRequest(request_text=text, context={"match_ids": [900001]}),
    )


def test_flags_are_opt_in(monkeypatch):
    monkeypatch.delenv("INSIDE_GAME_EXPERIMENTS", raising=False)
    assert T(40) == 40
    monkeypatch.setenv("INSIDE_GAME_EXPERIMENTS", "slow")
    monkeypatch.setenv("INSIDE_GAME_EXPERIMENT_TIME_SCALE", "3")
    assert T(40) == 120


def test_requested_visuals_and_topology_detection():
    text = (
        "Crea una página con el mapa de tiros del equipo 2 y una lectura de sus goles"
    )
    assert requested_visuals(text) == [("shot_map", "mapa de tiros")]
    assert not wants_topology(text)
    assert wants_topology("Analiza la forma del bloque y el espacio libre")


def test_tool_subset_keeps_discovery_and_falls_back_to_all():
    shots = tool_subset("Recupera todos los tiros del partido 900011", OPERATIONS)
    assert {"get_shots", "get_match_context", "describe_dataset"} <= shots
    assert "get_defensive_actions" not in shots
    assert tool_subset("Hola", OPERATIONS) == set(OPERATIONS)


class PlanModel:
    """Devuelve un plan de creación sin partido, como hacía el modelo local."""

    name = "plan-without-match"

    async def respond(self, instructions, messages, tools):
        from inside_game.providers.models import ModelTurn

        return ModelTurn(
            [
                {
                    "type": "function_call",
                    "call_id": str(uuid4()),
                    "name": "delegate_request",
                    "arguments": json.dumps(
                        {
                            "action": "create",
                            "title": "Mapa de tiros",
                            "reply": "Creo la página.",
                            "context": {"match_ids": [], "team_ids": [1]},
                            "data_request": "get_shots",
                            "analysis_request": "shot_map",
                        }
                    ),
                }
            ]
        )


def interpret(text, selected):
    from inside_game.agents.contracts import DataContext
    from inside_game.agents.interpreter import Interpreter

    return asyncio.run(
        Interpreter(PlanModel()).interpret(
            text=text,
            context=DataContext(match_ids=selected),
            history=[],
            matches=[{"match_id": 900001}, {"match_id": 900002}],
            report=None,
        )
    )


def test_interpreter_fills_known_match_only_with_guards(monkeypatch):
    import pytest

    from inside_game.providers.models import ModelFailure

    # main ya recupera un único partido seleccionado; la bandera añade el
    # partido nombrado en el texto cuando no hay selección.
    monkeypatch.delenv("INSIDE_GAME_EXPERIMENTS", raising=False)
    assert interpret("Mapa de tiros del equipo 1", [900001]).context.match_ids == [
        900001
    ]
    with pytest.raises(ModelFailure, match="INTERPRETER_INVALID_PLAN"):
        interpret("Mapa de tiros del partido 900002", [])

    monkeypatch.setenv("INSIDE_GAME_EXPERIMENTS", "guards")
    assert interpret("Mapa de tiros del equipo 1", [900001]).context.match_ids == [
        900001
    ]
    assert interpret("Mapa de tiros del partido 900002", []).context.match_ids == [
        900002
    ]
    with pytest.raises(ModelFailure):
        interpret("Mapa de tiros del partido 999999", [])


def test_team_guard_keeps_requested_team_only_when_it_plays():
    from inside_game.agents.contracts import DataContext
    from inside_game.agents.interpreter import team_ids_from

    matches = [
        {
            "match_id": 900001,
            "home_team_id": 1,
            "home_team_name": "Mock Objects FC",
            "away_team_id": 2,
            "away_team_name": "Test Fixtures United",
        }
    ]
    empty = DataContext()
    assert team_ids_from("Goles del equipo 2", empty, 900001, matches) == [2]
    assert team_ids_from("Tiros de Mock Objects FC", empty, 900001, matches) == [1]
    assert team_ids_from("Tiros del equipo 7", empty, 900001, matches) == []
    assert team_ids_from("Tiros del partido", empty, 900001, matches) == []
    assert team_ids_from("Compara equipo 1 y equipo 2", empty, 900001, matches) == [
        1,
        2,
    ]
    assert team_ids_from("x", DataContext(team_ids=[2]), 900001, matches) == [2]


def test_fast_path_decides_with_original_question(monkeypatch):
    from inside_game.agents.experiments import (
        original_question,
        with_original_question,
    )

    monkeypatch.delenv("INSIDE_GAME_EXPERIMENTS", raising=False)
    assert with_original_question("get_events", "¿Qué goles?") == "get_events"

    monkeypatch.setenv("INSIDE_GAME_EXPERIMENTS", "fastpath")
    text = with_original_question(
        "get_events, get_shots", "¿Qué goles marcó el equipo 2?"
    )
    assert original_question(text) == "¿Qué goles marcó el equipo 2?"
    assert original_question("sin pregunta original") == "sin pregunta original"


def test_label_mismatch_detects_goals_cited_as_shots():
    from inside_game.agents.analyst_facts import TOKEN
    from inside_game.agents.experiments import label_mismatches

    facts = {
        "f-000000000001": SimpleNamespace(label="goals"),
        "f-000000000002": SimpleNamespace(label="shots"),
        "f-000000000003": SimpleNamespace(label="xg"),
    }
    assert label_mismatches(
        "Realizó {{f-000000000001}} tiros con {{f-000000000003}} de xG.",
        facts,
        TOKEN,
    ) == [("f-000000000001", "goals", "tiros")]
    assert not label_mismatches(
        "Marcó {{f-000000000001}} goles en {{f-000000000002}} tiros "
        "({{f-000000000003}} de xG).",
        facts,
        TOKEN,
    )


def test_window_samples_are_summarized_only_with_flag(monkeypatch):
    import pytest

    from inside_game.agents.analyst_facts import evidence_facts, summarize_samples
    from inside_game.agents.contracts import Evidence

    shape = next(
        e for e in evidence_result().evidence if e.operation == "get_team_shape"
    )
    sample = shape.response.data["samples"][0]
    window = [
        {**sample, "time_ms": 1740000 + 1000 * i, "result": sample["result"]}
        for i in range(60)
    ]
    data = {**shape.response.data, "samples": window}
    evidence = Evidence.model_validate(
        {
            **shape.model_dump(mode="json"),
            "response": {**shape.response.model_dump(mode="json"), "data": data},
        }
    )

    monkeypatch.delenv("INSIDE_GAME_EXPERIMENTS", raising=False)
    with pytest.raises(ValueError, match="FACT_BUDGET_EXCEEDED"):
        evidence_facts([evidence])

    monkeypatch.setenv("INSIDE_GAME_EXPERIMENTS", "samples")
    facts = evidence_facts([evidence])
    assert 0 < len(facts) <= 220
    summary = summarize_samples(window)
    assert summary["samples"] == 60
    assert summary["time_ms_start"] == 1740000 and summary["time_ms_end"] == 1799000


def test_recipe_sources_cover_requested_visuals():
    from inside_game.agents.experiments import REQUESTED_VISUALS
    from inside_game.agents.page_builder import RECIPE_SOURCES

    assert all(recipe in RECIPE_SOURCES for _, recipe, _ in REQUESTED_VISUALS)


def test_requested_visuals_ignore_generic_block_and_accept_recipe_ids():
    added = requested_visuals(
        'Añade el bloque "Cronología del partido". Mantén los bloques existentes.'
    )
    assert added == [("match_timeline", "cronología")]
    assert requested_visuals("Incluir el bloque match_timeline") == [
        ("match_timeline", "cronología")
    ]
    assert requested_visuals("la forma del bloque en el minuto 30") == [
        ("team_shape", "forma del bloque")
    ]


def test_repair_hints_point_each_number_to_its_fact():
    from inside_game.agents.sports_analyst import repair_hints

    facts = [
        SimpleNamespace(id="f-000000000001", value=14, label="shots"),
        SimpleNamespace(id="f-000000000002", value=1.062, label="xg"),
        SimpleNamespace(id="f-000000000003", value=22.2, label="conversion_rate"),
    ]
    hints = repair_hints({"literal_numbers": ["14", "1.062", "22,2%", "99"]}, facts)
    assert hints["use_fact_for_number"]["14"] == [
        {"cite": "{{f-000000000001}}", "label": "shots"}
    ]
    assert hints["use_fact_for_number"]["1.062"][0]["label"] == "xg"
    assert hints["use_fact_for_number"]["22,2%"][0]["label"] == "conversion_rate"
    assert hints["numbers_without_fact"] == ["99"]
    assert repair_hints({"literal_numbers": []}, facts) == {}
