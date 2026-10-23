"""Read-only end-to-end verification against the configured Azure demo database.

Run explicitly: python scripts/verify_api.py. No synthetic rows are changed.
"""

import json
import time
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from inside_game.api import create_app
from inside_game.settings import Settings
from inside_game.tools.synthetic_db import SqlRepository


def verification_cases(d):
    first_shot = d["event_shots"][0]["event_id"]
    first_pass = next(
        p["event_id"] for p in d["event_passes"] if p["height"]["id"] == 1
    )
    snapshot = {"match_id": 900001, "team_id": 1, "period": 1, "time_ms": 600000}
    cases = {
        "describe_dataset": {},
        "find_entities": {
            "kind": "player",
            "name": "Synthetic",
            "match_id": 900001,
            "limit": 5,
        },
        "list_matches": {},
        "get_match_context": {"match_id": 900001},
        "get_team_summary": {
            "match_ids": [900001],
            "team_id": 1,
            "profile_id": "finishing",
        },
        "get_player_summary": {
            "match_ids": [900001],
            "player_id": 110,
            "profile_id": "passing",
        },
        "get_shots": {
            "match_id": 900001,
            "team_id": 1,
            "outcome": "on_target",
            "view": "summary",
        },
        "get_passes": {"match_id": 900001, "height": "high", "limit": 5},
        "get_defensive_actions": {
            "match_id": 900001,
            "kind": "aerial_duel",
            "limit": 5,
        },
        "get_ball_actions": {"match_id": 900001, "kind": "dribble", "limit": 5},
        "get_discipline": {"match_id": 900001, "limit": 5},
        "get_substitutions": {"match_id": 900001},
        "get_possessions": {"match_id": 900001, "limit": 5},
        "get_tracking_frame": {"match_id": 900001, "period": 1, "time_ms": 600000},
        "get_tracking_window": {
            "match_id": 900001,
            "scope": {
                "kind": "window",
                "period": 1,
                "start_ms": 600000,
                "end_ms": 610000,
            },
        },
        "get_event_context": {"event_id": first_shot},
        "get_heatmap": {
            "match_id": 900001,
            "player_id": 110,
            "mode": "occupancy_seconds",
        },
        "get_movement_summary": {"match_id": 900001, "team_id": 1},
        "get_metric_series": {
            "match_id": 900001,
            "team_id": 1,
            "profile_id": "finishing",
        },
        "compare_entities": {
            "match_ids": [900001],
            "entity_kind": "team",
            "entity_ids": [1, 2],
            "profile_id": "finishing",
        },
        "get_set_piece_sequences": {"match_id": 900001, "limit": 5},
        "get_events": {"match_id": 900001, "event_types": [10, 14], "limit": 5},
        "get_sequences": {
            "match_id": 900001,
            "pattern_id": "pressure_to_recovery",
            "limit": 5,
        },
        "get_zone_summary": {
            "match_id": 900001,
            "team_id": 1,
            "zone_id": "final_third",
        },
        "get_rankings": {
            "match_ids": [900001],
            "metric": "xg",
            "profile_id": "finishing",
            "limit": 5,
        },
        "get_team_shape": snapshot,
        "get_proximity_connectivity": {**snapshot, "view": "matrix"},
        "get_space_coverage": {**snapshot, "view": "triangulation"},
        "get_passing_network": {"match_id": 900001, "team_id": 1},
        "get_pass_corridor": {
            "match_id": 900001,
            "team_id": d["event_index"][first_pass]["team_id"],
            "event_id": first_pass,
        },
        "get_line_breaks": {"match_id": 900001, "team_id": 1},
        "get_persistent_structure": snapshot,
        "get_node_removal_robustness": snapshot,
        "get_defensive_profile": {"match_id": 900001, "team_id": 2},
    }
    return cases


def main():
    settings = Settings(
        api_key="live-verification-only-ephemeral-key", local_access=False
    )
    repo = SqlRepository(settings)
    cases = verification_cases(repo.match(900001))
    report = {
        "tested_at_utc": datetime.now(UTC).isoformat(),
        "source": "HTTP contracts backed by actual Azure SQL analytics views",
        "status": "running",
        "operations": [],
        "checks": [],
    }
    with TestClient(
        create_app(settings, repo), raise_server_exceptions=False
    ) as client:
        client.headers["Authorization"] = "Bearer " + settings.api_key
        for operation, body in cases.items():
            start = time.monotonic()
            response = client.post("/api/operations/" + operation, json=body)
            item = {
                "operation": operation,
                "status_code": response.status_code,
                "seconds": round(time.monotonic() - start, 3),
            }
            if response.status_code != 200:
                item["error"] = response.json()
            report["operations"].append(item)
            print(json.dumps(item), flush=True)

        def check(name, condition):
            report["checks"].append({"name": name, "passed": bool(condition)})

        def get(op, body):
            r = client.post("/api/operations/" + op, json=body)
            assert r.status_code == 200, r.text
            return r.json()["data"]

        check(
            "34 operations return HTTP 200",
            all(r["status_code"] == 200 for r in report["operations"])
            and len(report["operations"]) == 34,
        )
        shots = get(
            "get_shots",
            {
                "match_id": 900001,
                "team_id": 1,
                "outcome": "on_target",
                "view": "summary",
            },
        )
        check("Known home on-target total = 6", shots["total"] == 6)
        check(
            "Known total shots = 23",
            get("get_shots", {"match_id": 900001, "view": "summary"})["total"] == 23,
        )
        check(
            "Nine aerial contests are not doubled",
            get("get_defensive_actions", {"match_id": 900001, "kind": "aerial_duel"})[
                "total"
            ]
            == 9,
        )
        check(
            "Six substitutions",
            get("get_substitutions", {"match_id": 900001})["total"] == 6,
        )
        check(
            "Frame has 22 active players",
            len(
                get(
                    "get_tracking_frame",
                    {"match_id": 900001, "period": 1, "time_ms": 600000},
                )["frames"][0]["players"]
            )
            == 22,
        )
        movement = get("get_movement_summary", {"match_id": 900001, "team_id": 1})
        check(
            "Team minutes = 11 x 90",
            abs(sum(p["covered_seconds"] for p in movement["players"]) - 11 * 5400)
            < 1e-6,
        )
        voronoi = get("get_space_coverage", cases["get_space_coverage"])["samples"][0][
            "result"
        ]
        check(
            "Voronoi partitions 7140 square metres",
            abs(voronoi["area_sum_m2"] - 7140) < 1e-6,
        )
        check(
            "SQL request field rejected",
            client.post(
                "/api/operations/get_shots",
                json={"match_id": 900001, "sql": "SELECT 1"},
            ).status_code
            == 422,
        )
        before_after = get(
            "compare_entities",
            {
                "match_ids": [900001],
                "mode": "windows",
                "entity_kind": "team",
                "entity_ids": [1],
                "windows": [
                    {"kind": "period", "period": 1},
                    {"kind": "period", "period": 2},
                ],
            },
        )
        check("Comparison of two periods", len(before_after["reports"]) == 2)
        ppda = get(
            "get_team_summary",
            {"match_ids": [900001], "team_id": 1, "profile_id": "ppda_demo"},
        )
        check(
            "PPDA has opponent passes and defensive denominator",
            ppda["aggregate"]["opponent_regular_pass_attempts_own_60_percent"] > 0
            and ppda["aggregate"]["defensive_actions_opponent_60_percent"] > 0,
        )
        defense = get("get_defensive_profile", {"match_id": 900001, "team_id": 2})
        check(
            "Defensive profile has actual opponent-action anchors",
            defense["anchor_count"] > 0
            and len(defense["samples"]) == defense["anchor_count"],
        )
        pressure = get(
            "get_defensive_actions",
            {"match_id": 900001, "kind": "pressure", "view": "summary"},
        )
        check("Known pressure count = 249", pressure["total"] == 249)
        passing = get("get_passes", {"match_id": 900001, "view": "summary"})
        check("Known pass count = 576", passing["total"] == 576)
        ball = get(
            "get_ball_actions",
            {"match_id": 900001, "kind": "dribble", "view": "summary"},
        )
        check("Known dribble count = 77", ball["total"] == 77)
    report["status"] = (
        "passed" if all(c["passed"] for c in report["checks"]) else "failed"
    )
    Path("docs/api-verification.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "operations": len(cases),
                "checks": len(report["checks"]),
            }
        ),
        flush=True,
    )
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
