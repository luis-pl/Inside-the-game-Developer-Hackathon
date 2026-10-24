"""Regression checks for real provenance, subsecond tracking and absent fields."""

import importlib.util
from pathlib import Path

import pytest

from inside_game import contracts as c
from inside_game.dashboard.config import DashboardConfig
from inside_game.dashboard.gateway import EpisodeService
from inside_game.service import AnalyticsService


def test_high_resolution_sampling_is_explicit_and_unambiguous():
    scope = {"kind": "window", "period": 1, "start_ms": 0, "end_ms": 300000}
    assert (
        c.TrackingWindow(
            match_id=900011, scope=scope, sample_step_ms=200
        ).sample_step_ms
        == 200
    )
    with pytest.raises(ValueError):
        c.TrackingWindow(match_id=900011, scope=scope, sample_step_ms=200, stride_s=5)


def test_real_match_provenance_and_unknown_xg(repository):
    data = repository.match(900001)
    data["meta"]["is_synthetic"] = False
    data["meta"]["generator_version"] = "metrica-anonymized-1.0.0"
    for shot in data["event_shots"]:
        shot["statsbomb_xg"] = None
        shot["body_part"] = None
    response = AnalyticsService(repository).execute(
        "get_team_summary",
        c.TeamSummary(match_ids=[900001], team_id=1, profile_id="finishing"),
    )
    assert response.provenance["is_synthetic"] is False
    assert response.provenance["data_kinds"] == ["real_anonymized"]
    assert response.data["reports"][0]["metrics"]["xg"] is None
    assert any("Metrica" in warning for warning in response.warnings)
    assert not any("Synthetic football" in warning for warning in response.warnings)


def test_real_frames_keep_missing_players_and_ball_visible():
    frame = {"period_time_ms": 200, "players": [], "ball": None, "ball_in_play": False}
    result = EpisodeService._frame(frame, {}, require_complete=False)
    assert result["players"] == [] and result["ball"] is None
    assert result["timeMs"] == 200


def test_all_zones_keeps_source_passes_on_or_outside_the_touchline(repository):
    data = repository.match(900001)
    event = next(e for e in data["events"] if e["event_id"] in data["passes"])
    event["location_x"], event["location_y"] = 121, -0.1
    service = AnalyticsService(repository)
    all_passes = service.execute("get_passes", c.PassesRequest(match_id=900001))
    assert all_passes.data["total"] == len(data["passes"])
    assert event["event_id"] in {e["event_id"] for e in all_passes.data["items"]}
    zoned = service.execute(
        "get_passes", c.PassesRequest(match_id=900001, zone_id="final_third")
    )
    assert event["event_id"] not in {e["event_id"] for e in zoned.data["items"]}


def test_skillcorner_keeps_provider_and_unknown_endpoints_without_false_xg(repository):
    data = repository.match(900001)
    data["meta"].update(
        is_synthetic=False, provider="SkillCorner", data_kind="real_pseudonymized"
    )
    for p in data["event_passes"]:
        p["end_x"] = p["end_y"] = None
    service = AnalyticsService(repository)
    passing = service.execute(
        "get_team_summary",
        c.TeamSummary(match_ids=[900001], team_id=1, profile_id="passing"),
    )
    assert passing.data["reports"][0]["metrics"]["attempted_passes"] > 0
    assert passing.data["reports"][0]["metrics"]["total_pass_length_m"] is None
    assert passing.provenance["data_kinds"] == ["real_pseudonymized"]
    assert any("SkillCorner" in w for w in passing.warnings)
    assert not any("Metrica" in w for w in passing.warnings)
    finishing = service.execute(
        "get_team_summary", c.TeamSummary(match_ids=[900001], team_id=1)
    )
    assert finishing.data["reports"][0]["metrics"]["goals"] is None


def test_real_spatial_results_preserve_numeric_team_keys_and_fractional_intervals(
    repository,
):
    data = repository.match(900001)
    data["meta"]["is_synthetic"] = False
    for interval in data["lineup_positions"]:
        for key in ("from_time", "to_time"):
            interval[key] += ".000"
    response = AnalyticsService(repository).execute(
        "get_space_coverage",
        c.SpatialRequest(match_id=900001, team_id=1, period=1, time_ms=1000),
    )
    assert response.data["samples"][0]["result"]["area_sum_m2"] > 0


def test_anonymized_catalog_is_the_default_and_does_not_mix_history():
    class Operations:
        def execute(self, *_):
            return {
                "data": {
                    "items": [
                        {
                            "match_id": n,
                            "home_team_id": 1,
                            "away_team_id": 2,
                            "home_team_name": "A",
                            "away_team_name": "B",
                            "is_synthetic": synthetic,
                        }
                        for n, synthetic in ((900001, True), (900011, False))
                    ]
                }
            }

    assert [row["id"] for row in EpisodeService(Operations()).matches()] == [900011]


def test_import_clocks_preserve_milliseconds_and_missing_values():
    path = Path(__file__).resolve().parents[1] / "scripts/prepare_metrica.py"
    spec = importlib.util.spec_from_file_location("prepare_metrica", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.clock(300000) == "00:05:00.000"
    assert module.clock(12340) == "00:00:12.340"
    assert module.number("NaN") is None
    assert module.number("0") == 0


def test_dashboard_uses_existing_private_credential_without_copying_it(
    tmp_path, monkeypatch
):
    import json

    for name in (
        "INSIDE_GAME_API_URL",
        "INSIDE_GAME_API_KEY",
        "INSIDE_GAME_DATA_MCP_URL",
        "INSIDE_GAME_DATA_MCP_KEY",
        "INSIDE_GAME_DATA_MCP_CREDENTIAL_FILE",
    ):
        monkeypatch.delenv(name, raising=False)
    private = tmp_path / "credential.json"
    private.write_text(json.dumps({"key": "private-test-key-" * 3}))
    (tmp_path / ".env.local").write_text(
        f"INSIDE_GAME_DATA_MCP_URL=https://example.org/mcp\nINSIDE_GAME_DATA_MCP_CREDENTIAL_FILE={private}\n"
    )
    config = DashboardConfig.load(tmp_path)
    assert config.api_key == "private-test-key-" * 3
    assert config.api_url == "https://example.org"
