"""Compositor del agente de insights y su guardián, sin red ni LLM."""

import asyncio
import copy

from inside_game.agents.insights_agent.composer import compose
from inside_game.agents.insights_agent.contracts import (
    BlockPlan,
    InsightIntent,
    PlanLabels,
    QuerySpec,
    ResolvedPlan,
)
from inside_game.insights.demo import demo_manifest
from inside_game.tools.evidence_client import EvidenceClient

FIXTURE = {e["operation"]: e["response"] for e in demo_manifest()["evidence"]}


class FakeTransport:
    """Responde el fixture SINTÉTICO de la galería por operación."""

    def __init__(self, overrides=None, errors=None):
        self.responses = {**FIXTURE, **(overrides or {})}
        self.errors = errors or {}
        self.calls = []

    async def call(self, operation, arguments):
        self.calls.append((operation, arguments))
        if operation in self.errors:
            return None, self.errors[operation]
        return copy.deepcopy(self.responses[operation]), None


def run(coroutine):
    return asyncio.run(coroutine)


def shots_args():
    return {"match_id": 900001, "limit": 200}


def plan(blocks, queries):
    return ResolvedPlan(
        intent=InsightIntent(template_id="match_overview", match_id=900001),
        source="synthetic",
        labels=PlanLabels(
            match="Synthetic FC 1 vs Synthetic FC 2",
            home_team="Synthetic FC 1",
            away_team="Synthetic FC 2",
            focus_team="Synthetic FC 1",
            synthetic=True,
        ),
        queries=[QuerySpec(key=k, operation=o, arguments=a) for k, o, a in queries],
        blocks=[
            BlockPlan(id=i, insight_id=r, title=r, query_keys=keys, parameters={})
            for i, r, keys in blocks
        ],
        home_team_id=1,
        away_team_id=2,
        focus_team_id=1,
    )


def test_compose_renders_html_through_the_insights_mcp():
    resolved = plan(
        [("shots", "shot_map", ["q1"]), ("passes", "pass_map", ["q2"])],
        [
            ("q1", "get_shots", shots_args()),
            ("q2", "get_passes", {"match_id": 900001, "limit": 200}),
        ],
    )
    data = EvidenceClient(FakeTransport())
    result = run(compose(resolved, data, title="Resumen SINTÉTICO"))
    assert [b.id for b in result.blocks] == ["shots", "passes"]
    assert all(b.state == "ready" and b.evidence_ids for b in result.blocks)
    assert result.blocks[0].metrics
    assert "Resumen SINTÉTICO" in result.html and "<svg" in result.html
    assert not result.discarded and result.evidence_count == 2


def test_guardian_hides_failed_unavailable_and_zero_only_blocks_with_reasons():
    no_xg = copy.deepcopy(FIXTURE["get_shots"])
    for event in no_xg["data"]["items"]:
        event["shot"]["statsbomb_xg"] = None
    zeros = copy.deepcopy(FIXTURE["get_ball_actions"])
    zeros["data"]["items"] = []
    zeros["data"]["summary"] = {"observed_events": 0}
    transport = FakeTransport(
        overrides={"get_shots": no_xg, "get_ball_actions": zeros},
        errors={"get_line_breaks": "SOURCE_FIELD_UNAVAILABLE"},
    )
    resolved = plan(
        [
            ("passes", "pass_map", ["q2"]),
            ("xg", "xg_story", ["q1", "q3"]),
            ("carries", "ball_progression", ["q4"]),
            ("lines", "defensive_geometry", ["q5", "q2"]),
        ],
        [
            ("q1", "get_shots", shots_args()),
            ("q2", "get_passes", {"match_id": 900001, "limit": 200}),
            ("q3", "get_metric_series", {"match_id": 900001, "limit": 200}),
            ("q4", "get_ball_actions", {"match_id": 900001, "limit": 200}),
            ("q5", "get_line_breaks", {"match_id": 900001, "team_id": 1}),
        ],
    )
    result = run(compose(resolved, EvidenceClient(transport), title="Guardián"))
    assert [b.id for b in result.blocks] == ["passes"]
    reasons = {d.insight_id: d.reason for d in result.discarded}
    assert "SOURCE_FIELD_UNAVAILABLE" in reasons["defensive_geometry"]
    assert "xG" in reasons["xg_story"]
    assert "en cero" in reasons["ball_progression"]
    assert result.api_errors == {"q5": "SOURCE_FIELD_UNAVAILABLE"}


def test_nothing_to_show_returns_no_html_but_keeps_every_reason():
    transport = FakeTransport(errors={"get_shots": "API_UNAVAILABLE"})
    resolved = plan(
        [("shots", "shot_map", ["q1"])], [("q1", "get_shots", shots_args())]
    )
    result = run(compose(resolved, EvidenceClient(transport), title="Vacío"))
    assert result.html is None and not result.blocks
    assert "API_UNAVAILABLE" in result.discarded[0].reason


def test_measured_source_keeps_a_real_zero_visible_with_a_note():
    # Un medio sin tiros en una fuente que sí anota tiros: el cero es información.
    zeros = copy.deepcopy(FIXTURE["get_ball_actions"])
    zeros["data"]["items"] = []
    zeros["data"]["summary"] = {"observed_events": 0}
    resolved = plan(
        [("carries", "ball_progression", ["q4"])],
        [("q4", "get_ball_actions", {"match_id": 900001, "limit": 200})],
    )
    resolved.profile_measured = True
    transport = FakeTransport(overrides={"get_ball_actions": zeros})
    result = run(compose(resolved, EvidenceClient(transport), title="Cero real"))
    assert [b.id for b in result.blocks] == ["carries"]
    assert any("Cero registrado" in w for w in result.blocks[0].warnings)


def _zero_ball_actions_report(**extra):
    manifest = demo_manifest()
    evidence = [
        copy.deepcopy(e) for e in manifest["evidence"] if e["evidence_id"] == "e7"
    ]
    evidence[0]["response"]["data"]["items"] = []
    evidence[0]["response"]["data"]["summary"] = {"observed_events": 0}
    blocks = [b for b in manifest["blocks"] if b["id"] == "ball_progression"]
    return {"title": "Ceros", "blocks": blocks, "evidence": evidence, **extra}


def test_adapter_marks_zero_only_recipe_as_empty_when_the_source_does_not_annotate_it():
    from inside_game.insights.pages import compile_report

    _, [block] = compile_report(
        _zero_ball_actions_report(zero_only_insights=["ball_progression"])
    )
    assert block.state == "empty_with_coverage"
    assert any("cobertura" in w for w in block.warnings)


def test_adapter_keeps_a_zero_ready_when_the_recipe_is_not_in_the_zero_only_profile():
    from inside_game.insights.pages import compile_report

    _, [block] = compile_report(_zero_ball_actions_report())
    assert block.state == "ready"


def test_composer_hides_a_zero_only_recipe_from_the_plan_profile_with_a_reason():
    zeros = copy.deepcopy(FIXTURE["get_ball_actions"])
    zeros["data"]["items"] = []
    zeros["data"]["summary"] = {"observed_events": 0}
    resolved = plan(
        [("carries", "ball_progression", ["q4"])],
        [("q4", "get_ball_actions", {"match_id": 900001, "limit": 200})],
    )
    resolved.profile_measured = True
    resolved.zero_only_insights = ["ball_progression"]
    transport = FakeTransport(overrides={"get_ball_actions": zeros})
    result = run(compose(resolved, EvidenceClient(transport), title="Perfil"))
    assert not result.blocks
    assert [d.insight_id for d in result.discarded] == ["ball_progression"]


def test_query_failure_reason_is_readable_and_keeps_the_error_code():
    from inside_game.agents.insights_agent.composer import _query_failure

    text = _query_failure(["SOURCE_FIELD_UNAVAILABLE", "CODIGO_NUEVO"])
    assert "la fuente no anota" in text and "(SOURCE_FIELD_UNAVAILABLE)" in text
    assert "CODIGO_NUEVO" in text
    assert _query_failure([]).endswith("sin evidencia")


def test_final_html_drops_unannotated_zeros_but_keeps_real_values():
    # El perfil de la fuente llega hasta el render final, no sólo al guardián.
    actions = copy.deepcopy(FIXTURE["get_ball_actions"])
    actions["data"]["summary"] = {"dribble_attempts": 0, "carries": 4}
    resolved = plan(
        [("carries", "ball_progression", ["q4"])],
        [("q4", "get_ball_actions", {"match_id": 900001, "limit": 200})],
    )
    resolved.unannotated_metrics = {"ball_progression": ["dribble_attempts"]}
    transport = FakeTransport(overrides={"get_ball_actions": actions})
    result = run(compose(resolved, EvidenceClient(transport), title="Perfil"))
    assert result.html and "Conducciones" in result.html
    assert "Regates intentados" not in result.html
    plain = plan(
        [("carries", "ball_progression", ["q4"])],
        [("q4", "get_ball_actions", {"match_id": 900001, "limit": 200})],
    )
    again = run(compose(plain, EvidenceClient(transport), title="Sin perfil"))
    assert "Regates intentados" in again.html, "sin perfil, un cero sigue siendo cero"
