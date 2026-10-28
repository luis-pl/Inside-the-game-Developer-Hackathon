"""EXPERIMENTO LOCAL: cambios activables con INSIDE_GAME_EXPERIMENTS."""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

from inside_game.agents.analyst_contracts import AnalysisRequest, FinishAnalysis
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


def test_task_state_tracks_requested_visual_and_outdated_page():
    state = run_for("Mapa de tiros del equipo 2 y lectura de sus goles")
    assert "Página: pendiente" in state.task_state()
    assert "mapa de tiros [PENDIENTE]" in state.task_state()

    state.merge(evidence_result())
    state.visual = SimpleNamespace(blocks=[{"id": "xg_story"}], report_id=uuid4())
    text = state.task_state()
    assert "generada con xg_story" in text
    assert "pidiendo lo que falta: mapa de tiros" in text

    state.merge(evidence_result())
    assert state.page_outdated
    assert "DESACTUALIZADA" in state.task_state()


def test_ensure_page_regenerates_missing_page_only_with_graceful(monkeypatch):
    insights = Insights([{"id": "shot_map"}])
    finish = FinishAnalysis(status="partial", sections=[])

    monkeypatch.delenv("INSIDE_GAME_EXPERIMENTS", raising=False)
    state = run_for("Mapa de tiros del equipo 2", insights)
    state.merge(evidence_result())
    asyncio.run(state.ensure_page(finish))
    assert insights.calls == [] and state.visual is None

    monkeypatch.setenv("INSIDE_GAME_EXPERIMENTS", "graceful")
    asyncio.run(state.ensure_page(finish))
    assert len(insights.calls) == 1
    assert insights.calls[0][0].startswith("mapa de tiros")
    assert state.visual is not None and not state.page_outdated


class FlakyInsights(Insights):
    """El primer intento no publica página; el segundo sí."""

    async def preview(self, request, *, timeout):
        result, payload = await super().preview(request, timeout=timeout)
        if len(self.calls) == 1:
            result.report_id = None
        return result, payload


def test_ensure_page_falls_back_to_available_charts(monkeypatch):
    monkeypatch.setenv("INSIDE_GAME_EXPERIMENTS", "graceful")
    insights = FlakyInsights([{"id": "shot_map"}])
    state = run_for("Compara los tiros de los dos equipos", insights)
    state.merge(evidence_result())
    asyncio.run(state.ensure_page(FinishAnalysis(status="partial", sections=[])))
    assert len(insights.calls) == 2
    assert insights.calls[0][0].startswith("comparación")
    assert "sólo con los gráficos que se puedan construir" in insights.calls[1][0]
    assert state.has_page() and not state.insights_failed


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

    monkeypatch.delenv("INSIDE_GAME_EXPERIMENTS", raising=False)
    with pytest.raises(ModelFailure, match="INTERPRETER_INVALID_PLAN"):
        interpret("Mapa de tiros del equipo 1", [900001])

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


def test_finish_publishes_valid_statements_after_repeated_rejection(monkeypatch):
    import pytest

    from inside_game.agents.sports_analyst import GroundingError

    monkeypatch.setenv("INSIDE_GAME_EXPERIMENTS", "graceful")
    state = run_for("Lectura del equipo")
    state.merge(evidence_result())
    state.reviewed = True
    good = state.facts[0].id
    args = FinishAnalysis.model_validate(
        {
            "status": "complete",
            "sections": [
                {
                    "heading": "Lectura",
                    "statements": [
                        {
                            "kind": "observation",
                            "text": "Dato verificado {{" + good + "}}.",
                            "fact_ids": [good],
                        },
                        {
                            "kind": "observation",
                            "text": "Hubo 99 tiros escritos a mano.",
                            "fact_ids": [good],
                        },
                    ],
                }
            ],
        }
    )
    with pytest.raises(GroundingError):
        state.finish(args.model_copy(deep=True))
    result = state.finish(args.model_copy(deep=True))
    assert result.status == "partial"
    assert "99 tiros" not in result.text
    assert any("Se omitieron 1" in item for item in result.limitations)


def test_spent_budget_message(monkeypatch):
    monkeypatch.setenv("INSIDE_GAME_EXPERIMENTS", "graceful,state")
    state = run_for("Mapa de tiros del equipo 2")
    state.merge(evidence_result())
    state.previews = state.agent.limits.max_visual_requests
    assert "no quedan peticiones de gráficos" in state.task_state()


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
