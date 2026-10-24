"""Regression: real 5 Hz replay and the merged Hodge pass network coexist."""

from inside_game.dashboard.gateway import EpisodeService


def test_real_five_minute_window_keeps_missing_tracking_and_hodge_passes():
    calls = []

    class RealOperations:
        def execute(self, operation, arguments):
            calls.append((operation, arguments))
            if operation == "get_match_context":
                return {
                    "data": {
                        "match": {
                            "match_id": 900011,
                            "home_team_id": 1,
                            "away_team_id": 2,
                            "home_team_name": "A",
                            "away_team_name": "B",
                            "is_synthetic": False,
                            "provider": "Metrica Sports",
                            "data_kind": "real_anonymized",
                        },
                        "periods": [
                            {
                                "period": 1,
                                "run_id": "observed",
                                "duration_ms": 300000,
                                "home_attacks_positive_x": True,
                            }
                        ],
                        "runs": [{"run_id": "observed", "sample_rate_hz": 5}],
                        "lineups": [
                            {
                                "player_id": p,
                                "team_id": 1,
                                "player_name": f"P{p}",
                                "jersey_number": p,
                            }
                            for p in (1, 2)
                        ],
                    }
                }
            if operation == "get_tracking_window":
                scope = arguments["scope"]
                assert arguments["sample_step_ms"] == 200
                assert scope["end_ms"] - scope["start_ms"] <= 20000
                return {
                    "data": {
                        "frames": [
                            {
                                "period_time_ms": t,
                                "players": [
                                    {
                                        "player_id": p,
                                        "team_id": 1,
                                        "on_pitch_slot": p,
                                        "is_on_pitch": True,
                                        "position_status": "available",
                                        "x_m": 20 + p,
                                        "y_m": 30,
                                    }
                                    for p in (1, 2)
                                ],
                                "ball": None,
                                "ball_in_play": False,
                            }
                            for t in range(scope["start_ms"], scope["end_ms"], 200)
                        ]
                    }
                }
            if operation == "get_passes":
                return {
                    "data": {
                        "items": [
                            {
                                "event_id": "observed-pass",
                                "player_id": 1,
                                "team_id": 1,
                                "period_time_ms": 1000,
                                "pass": {"recipient_player_id": 2, "outcome": None},
                            }
                        ]
                    }
                }
            return {"data": {"items": []}}

    episode = EpisodeService(RealOperations()).episode(900011, 1, 0, 300)
    assert len(episode["frames"]) == 1500
    assert episode["window"] == {"startMs": 0, "endMs": 300000, "sampleStepMs": 200}
    assert all(len(f["players"]) == 2 and f["ball"] is None for f in episode["frames"])
    assert episode["provider"] == "Metrica Sports"
    assert episode["dataKind"] == "real_anonymized"
    assert episode["passes"] == [
        {"id": "observed-pass", "source": 1, "target": 2, "teamId": 1, "timeMs": 1000}
    ]
    assert len([op for op, _ in calls if op == "get_tracking_window"]) == 15
