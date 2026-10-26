"""Resolvedor del agente de insights: decisiones deterministas sin LLM ni red."""

import asyncio

import pytest
from pydantic import ValidationError

from inside_game.agents.insights_agent.contracts import InsightIntent
from inside_game.agents.insights_agent.profiles import build_profiles, zero_only
from inside_game.agents.insights_agent.resolver import (
    Resolver,
    orientation,
    source_roles,
)
from inside_game.insights.catalog import RECIPES
from inside_game.insights.contracts import Parameters
from inside_game.service import OPERATIONS

HOME, AWAY = 1, 2


def interval(player_id, team_id, position):
    return {
        "player_id": player_id,
        "team_id": team_id,
        "position": position,
        "from_time": "00:00",
        "to_time": "90:00.000",
        "from_period": 1,
        "to_period": 2,
    }


def context(annotated=True):
    positions = [
        "Goalkeeper",
        "Right Back",
        "Center Back",
        "Left Back",
        "Center Defensive Midfield",
        "Center Forward",
    ]
    intervals = []
    for team_id in (HOME, AWAY):
        for n, position in enumerate(positions):
            label = position if annotated or position == "Goalkeeper" else None
            intervals.append(interval(team_id * 100 + n + 1, team_id, label))
    return {
        "match": {
            "match_id": 900001,
            "home_team_id": HOME,
            "away_team_id": AWAY,
            "home_team_name": "Local",
            "away_team_name": "Visitante",
            "is_synthetic": True,
            "provider": None,
        },
        "lineups": [
            {"team_id": i["team_id"], "player_id": i["player_id"]} for i in intervals
        ],
        "position_intervals": intervals,
        "periods": [
            {"period": 1, "home_attacks_positive_x": True, "duration_ms": 2700000},
            {"period": 2, "home_attacks_positive_x": False, "duration_ms": 2700000},
        ],
    }


def page(data):
    return {"response": {"data": data}}


class FakeData:
    """Responde contexto, sondas de cobertura y pases; registra las llamadas."""

    def __init__(
        self,
        ctx=None,
        covered=None,
        pass_times=(645680, 655000, 662000, 671000),
        shots=(),
    ):
        self.ctx = ctx or context()
        self.covered = covered
        self.pass_times = pass_times
        self.shots = shots
        self.calls = []

    async def __call__(self, operation, arguments):
        self.calls.append((operation, arguments))
        if operation == "get_match_context":
            return [page(self.ctx)], None
        if operation == "get_team_shape":
            if self.covered is None or arguments["time_ms"] in self.covered:
                return [page({})], None
            return [], "get_team_shape: HTTP 422 INSUFFICIENT_COVERAGE"
        if operation == "get_passes":
            items = [
                {"period_time_ms": t, "pass": {"outcome": None}}
                for t in self.pass_times
            ]
            return [page({"items": items})], None
        if operation == "get_shots":
            return [page({"items": list(self.shots)})], None
        raise AssertionError(operation)


def resolve(intent, fetch=None, **kwargs):
    kwargs.setdefault("profiles", {})
    return asyncio.run(Resolver(fetch or FakeData(), **kwargs).resolve(intent))


def test_intent_rejects_incomplete_requests():
    with pytest.raises(ValidationError):
        InsightIntent(template_id="player_dossier", match_id=1)
    with pytest.raises(ValidationError):
        InsightIntent(template_id="custom_report", match_id=1, insight_ids=["xg_magic"])
    with pytest.raises(ValidationError):
        InsightIntent(template_id="tactical_episode", match_id=1, time_ms=1000)
    with pytest.raises(ValidationError):
        InsightIntent(template_id="match_overview", match_id=1, plan="drop table")
    # Una comparación de equipos con IDs explícitos exige dos distintos;
    # vacío significa local y visitante.
    with pytest.raises(ValidationError):
        InsightIntent(
            template_id="entity_comparison",
            match_id=1,
            compare_kind="team",
            compare_ids=[1],
        )
    with pytest.raises(ValidationError):
        InsightIntent(
            template_id="entity_comparison",
            match_id=1,
            compare_kind="team",
            compare_ids=[1, 1],
        )


def test_player_team_wins_over_a_stale_conflicting_team():
    plan = resolve(
        {
            "template_id": "player_dossier",
            "match_id": 900001,
            "player_id": 105,
            "team_id": AWAY,
        }
    )
    assert plan.intent.team_id == HOME
    assert plan.focus_team_id == HOME
    assert plan.decisions["team_adjusted_from"] == AWAY
    assert plan.decisions["focus_team"] == "equipo del jugador (ajustado)"


def test_roles_come_from_source_positions_never_from_jersey():
    roles = source_roles(context(), HOME, 1, 600000)
    assert roles == {
        "goalkeeper_id": 101,
        "defender_ids": [102, 103, 104],
        "midfielder_ids": [105],
    }
    # Metrica: sólo el portero está anotado; no se inventan defensores.
    assert source_roles(context(annotated=False), HOME, 1, 600000) == {
        "goalkeeper_id": 101
    }


def test_orientation_is_inverted_for_the_away_team_and_by_period():
    ctx = context()
    assert orientation(ctx, HOME, 1) is True
    assert orientation(ctx, AWAY, 1) is False
    assert orientation(ctx, HOME, 2) is False


def test_every_recipe_resolves_to_valid_operations_and_parameters():
    plan = resolve(
        {
            "template_id": "custom_report",
            "match_id": 900001,
            "period": 1,
            "insight_ids": list(RECIPES),
        },
        apply_profile=False,
    )
    assert {b.insight_id for b in plan.blocks} == set(RECIPES)
    assert not plan.discarded
    keys = {q.key for q in plan.queries}
    for query in plan.queries:
        OPERATIONS[query.operation].model_validate(query.arguments)
    for block in plan.blocks:
        assert set(block.query_keys) <= keys
        Parameters.model_validate(block.parameters)
        operations = {q.operation for q in plan.queries if q.key in block.query_keys}
        assert operations & set(RECIPES[block.insight_id]["source_operations"])
    identities = [(q.operation, str(q.arguments)) for q in plan.queries]
    assert len(identities) == len(set(identities))


def test_profile_discards_impossible_and_misleading_recipes_with_reason():
    profiles = {
        "synthetic": {
            "unavailable": {"xg_story": "xG no disponible."},
            "zero_only": {"defensive_actions": "Ceros que no significan ausencia."},
        }
    }
    plan = resolve(
        {"template_id": "match_overview", "match_id": 900001}, profiles=profiles
    )
    shown = {b.insight_id for b in plan.blocks}
    assert "xg_story" not in shown and "defensive_actions" not in shown
    reasons = {d.insight_id: d.reason for d in plan.discarded}
    assert reasons == {
        "xg_story": "xG no disponible.",
        "defensive_actions": "Ceros que no significan ausencia.",
    }


def test_snapshot_uses_first_instant_with_full_coverage():
    fetch = FakeData(covered={900000})
    plan = resolve({"template_id": "tactical_episode", "match_id": 900001}, fetch)
    assert plan.decisions["time_ms"] == 900000
    shape = next(b for b in plan.blocks if b.insight_id == "team_shape")
    assert shape.parameters["time_ms"] == 900000
    # La pieza de un instante lo dice en su título.
    assert shape.title.endswith("· P1 15:00")
    whole_match = next(b for b in plan.blocks if b.insight_id == "play_replay")
    assert "P1 15:00" not in whole_match.title


def test_requested_instant_is_aligned_adjusted_and_reported():
    fetch = FakeData(covered={605000})
    plan = resolve(
        {
            "template_id": "tactical_episode",
            "match_id": 900001,
            "period": 1,
            "time_ms": 600400,
        },
        fetch,
    )
    assert plan.decisions["time_ms"] == 605000
    assert plan.decisions["instant_adjusted_from_ms"] == 600000


def test_no_covered_instant_discards_only_snapshot_recipes():
    plan = resolve(
        {"template_id": "tactical_episode", "match_id": 900001}, FakeData(covered=set())
    )
    shown = {b.insight_id for b in plan.blocks}
    assert "team_shape" not in shown and "play_replay" in shown
    assert any("posicionados" in d.reason for d in plan.discarded)


def test_pass_window_is_anchored_on_passes_and_aligned_to_seconds():
    plan = resolve({"template_id": "tactical_episode", "match_id": 900001})
    window = plan.decisions["pass_windows"][str(HOME)]
    assert window == {
        "kind": "window",
        "period": 1,
        "start_ms": 640000,
        "end_ms": 700000,
    }
    structural = next(b for b in plan.blocks if b.insight_id == "structural_pass")
    scopes = [
        q.arguments["scope"] for q in plan.queries if q.key in structural.query_keys
    ]
    assert all(s == window for s in scopes)


def test_pass_window_falls_back_to_earlier_passes_then_discards():
    early = resolve(
        {"template_id": "tactical_episode", "match_id": 900001},
        FakeData(pass_times=(100000, 110000, 120000)),
    )
    assert early.decisions["pass_windows"][str(HOME)]["start_ms"] == 95000
    none = resolve(
        {"template_id": "tactical_episode", "match_id": 900001},
        FakeData(pass_times=(100000,)),
    )
    assert {"structural_pass", "between_lines_receptions"} <= {
        d.insight_id for d in none.discarded
    }


def test_between_lines_uses_the_rival_lines_and_team_orientation():
    plan = resolve(
        {"template_id": "tactical_episode", "match_id": 900001, "team_id": AWAY}
    )
    block = next(b for b in plan.blocks if b.insight_id == "between_lines_receptions")
    assert block.parameters["team_id"] == AWAY
    assert block.parameters["defender_ids"] == [102, 103, 104]
    assert block.parameters["midfielder_ids"] == [105]
    assert block.parameters["attack_positive_x"] is False


def test_unannotated_roles_discard_role_recipes_instead_of_guessing():
    plan = resolve(
        {"template_id": "tactical_episode", "match_id": 900001},
        FakeData(ctx=context(annotated=False)),
    )
    discarded = {d.insight_id for d in plan.discarded}
    assert {"defensive_line_height", "between_lines_receptions"} <= discarded
    assert "structural_pass" in {b.insight_id for b in plan.blocks}


def test_both_teams_get_separate_blocks_and_player_dossier_filters_player():
    overview = resolve({"template_id": "match_overview", "match_id": 900001})
    networks = [b for b in overview.blocks if b.insight_id == "passing_network"]
    assert [b.parameters["team_id"] for b in networks] == [HOME, AWAY]
    assert networks[0].id != networks[1].id
    dossier = resolve(
        {"template_id": "player_dossier", "match_id": 900001, "player_id": 105}
    )
    assert all(b.parameters.get("player_id") == 105 for b in dossier.blocks)


def test_profiles_mark_zero_only_ready_blocks_as_misleading():
    row = {"state": "ready", "items": {}, "metrics": {"tackles_won": 0, "rate": None}}
    assert zero_only(row)
    assert not zero_only({**row, "metrics": {"seconds": 12.0}})
    report = {
        "matches": [
            {
                "match_id": 9,
                "is_synthetic": False,
                "provider": "SkillCorner",
                "insights": {
                    "defensive_actions": row,
                    "xg_story": {"state": "unavailable", "reasons": ["Sin xG."]},
                    "shot_map": {"state": "ready", "items": {"points": 3}},
                },
            }
        ]
    }
    profile = build_profiles(report)["SkillCorner"]
    assert profile["unavailable"] == {"xg_story": "Sin xG."}
    assert set(profile["zero_only"]) == {"defensive_actions"}


def test_custom_report_honors_the_requested_team_on_match_pieces():
    # "¿Desde dónde remató el visitante?": los tiros y su xG sólo de ese equipo.
    plan = resolve(
        {
            "template_id": "custom_report",
            "match_id": 900001,
            "team_id": AWAY,
            "insight_ids": ["shot_map", "xg_story", "match_timeline"],
        }
    )
    by_recipe = {b.insight_id: b for b in plan.blocks}
    queries = {q.key: q for q in plan.queries}
    for key in ("shot_map", "xg_story"):
        assert by_recipe[key].parameters["team_id"] == AWAY
        assert all(
            queries[k].arguments["team_id"] == AWAY for k in by_recipe[key].query_keys
        )
    # La cronología sigue siendo del partido completo.
    assert "team_id" not in by_recipe["match_timeline"].parameters


def shot(period, time_ms, outcome="Saved", xg=None):
    return {
        "period": period,
        "period_time_ms": time_ms,
        "shot": {"outcome": {"name": outcome}, "statsbomb_xg": xg},
    }


def test_tactical_episode_anchors_on_a_goal_before_other_shots():
    fetch = FakeData(shots=[shot(1, 300000, xg=0.9), shot(2, 1500000, "Goal", xg=0.1)])
    plan = resolve({"template_id": "tactical_episode", "match_id": 900001}, fetch)
    assert (plan.decisions["period"], plan.decisions["time_ms"]) == (2, 1500000)
    assert plan.decisions["moment"] == "gol del equipo protagonista"


def test_tactical_episode_uses_the_highest_xg_shot_without_goals_and_respects_period():
    fetch = FakeData(shots=[shot(1, 300000, xg=0.1), shot(1, 900000, xg=0.6)])
    plan = resolve({"template_id": "tactical_episode", "match_id": 900001}, fetch)
    assert plan.decisions["time_ms"] == 900000
    assert "mayor xG" in plan.decisions["moment"]
    only_second = FakeData(shots=[shot(1, 900000, xg=0.6), shot(2, 1200000, xg=0.2)])
    plan = resolve(
        {"template_id": "tactical_episode", "match_id": 900001, "period": 2},
        only_second,
    )
    assert (plan.decisions["period"], plan.decisions["time_ms"]) == (2, 1200000)


def test_tactical_episode_skips_a_moment_without_coverage_and_never_overrides_a_request():
    covered = FakeData(
        covered={1200000}, shots=[shot(1, 600000, "Goal"), shot(1, 1200000)]
    )
    plan = resolve({"template_id": "tactical_episode", "match_id": 900001}, covered)
    assert plan.decisions["time_ms"] == 1200000
    requested = FakeData(shots=[shot(1, 300000, "Goal")])
    plan = resolve(
        {
            "template_id": "tactical_episode",
            "match_id": 900001,
            "period": 1,
            "time_ms": 600000,
        },
        requested,
    )
    assert plan.decisions["time_ms"] == 600000 and "moment" not in plan.decisions
    assert not [c for c in requested.calls if c[0] == "get_shots"]


def test_tactical_episode_without_shots_keeps_the_default_instant():
    plan = resolve({"template_id": "tactical_episode", "match_id": 900001})
    assert plan.decisions["time_ms"] == 600000 and "moment" not in plan.decisions


def test_tactical_episode_without_xg_uses_the_shot_closest_to_goal():
    def located(time_ms, x, y):
        return {**shot(1, time_ms, "Unknown"), "attacking_x_m": x, "attacking_y_m": y}

    fetch = FakeData(shots=[located(15000, 80.0, 10.0), located(900000, 98.0, 33.0)])
    plan = resolve({"template_id": "tactical_episode", "match_id": 900001}, fetch)
    assert plan.decisions["time_ms"] == 900000
    assert "más cercano a portería" in plan.decisions["moment"]


def test_goalkeeper_dossier_drops_outfield_pieces_but_an_outfielder_keeps_them():
    keeper = resolve(
        {"template_id": "player_dossier", "match_id": 900001, "player_id": 101}
    )
    outfielder = resolve(
        {"template_id": "player_dossier", "match_id": 900001, "player_id": 102}
    )
    dropped = {"shot_map", "ball_progression", "defensive_actions"}
    assert dropped.isdisjoint({b.insight_id for b in keeper.blocks})
    assert dropped <= {d.insight_id for d in keeper.discarded}
    assert any("portero" in d.reason for d in keeper.discarded)
    assert dropped <= {b.insight_id for b in outfielder.blocks}


def test_moment_is_reported_when_coverage_forces_a_nearby_instant():
    fetch = FakeData(covered={605000}, shots=[shot(1, 600000, "Goal")])
    plan = resolve({"template_id": "tactical_episode", "match_id": 900001}, fetch)
    assert plan.decisions["time_ms"] == 605000
    assert plan.decisions["moment_ms"] == 600000
    assert plan.decisions["moment"] == "gol del equipo protagonista"
