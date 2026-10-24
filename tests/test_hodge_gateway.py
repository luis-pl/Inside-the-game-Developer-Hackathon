"""Completed-pass integration: pagination, identity and failure semantics."""

import unittest

from inside_game.dashboard.gateway import DataError, EpisodeService


def event(id, sender=1, target=2, outcome=None):
    return {
        "event_id": id,
        "player_id": sender,
        "team_id": 1,
        "period_time_ms": 1000,
        "pass": {"recipient_player_id": target, "outcome": outcome},
    }


class HodgeGatewayTests(unittest.TestCase):
    def test_pagination_and_unattributed_passes(self):
        calls = []

        class Pages:
            def execute(self, operation, arguments):
                calls.append((operation, arguments))
                if "cursor" not in arguments:
                    return {
                        "data": {"items": [event("one")]},
                        "pagination": {"next_cursor": "next"},
                    }
                return {
                    "data": {"items": [event("two", 2, 1), event("unknown", 1, None)]},
                    "pagination": {},
                }

        rows, warnings = EpisodeService(Pages())._completed_passes(
            1, 1, 0, 60000, {1: {"team_id": 1}, 2: {"team_id": 1}}
        )
        self.assertEqual([r["id"] for r in rows], ["one", "two"])
        self.assertEqual(calls[0][0], "get_passes")
        self.assertEqual(calls[0][1]["outcome"], "complete")
        self.assertEqual(calls[1][1]["cursor"], "next")
        self.assertIn("1 pases omitidos", warnings[0])

    def test_incomplete_pass_or_duplicate_page_is_not_used(self):
        class Invalid:
            def __init__(self, incomplete):
                self.incomplete = incomplete

            def execute(self, *_):
                return {
                    "data": {
                        "items": [
                            event(
                                "same",
                                outcome="Incomplete" if self.incomplete else None,
                            )
                        ]
                    },
                    "pagination": {"next_cursor": "repeat"},
                }

        for incomplete in (True, False):
            with self.assertRaises(DataError):
                EpisodeService(Invalid(incomplete))._completed_passes(
                    1, 1, 0, 60000, {1: {"team_id": 1}, 2: {"team_id": 1}}
                )

    def test_failed_pass_query_is_unavailable_not_zero(self):
        class Partial:
            def execute(self, operation, _):
                if operation == "get_match_context":
                    return {
                        "data": {
                            "match": {
                                "match_id": 1,
                                "home_team_id": 1,
                                "away_team_id": 2,
                                "home_team_name": "A",
                                "away_team_name": "B",
                            },
                            "lineups": [],
                            "periods": [
                                {
                                    "period": 1,
                                    "run_id": "run",
                                    "duration_ms": 1000,
                                    "home_attacks_positive_x": True,
                                }
                            ],
                        }
                    }
                if operation == "get_tracking_window":
                    return {"data": {"frames": [{"timeMs": 0}]}}
                if operation == "get_passes":
                    raise DataError("Unavailable")
                return {"data": {"items": []}}

        service = EpisodeService(Partial())
        from unittest.mock import patch

        with patch.object(EpisodeService, "_frame", return_value={"timeMs": 0}):
            result = service.episode(1, 1, 0)
        self.assertIsNone(result["passes"])
        self.assertTrue(any("Hodge no disponible" in w for w in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
