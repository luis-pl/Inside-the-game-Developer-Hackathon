"""Isolated adapter tests; no Azure, SQL, model key or third-party packages."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from inside_game.dashboard.config import DashboardConfig
from inside_game.dashboard.gateway import DataError, EpisodeService, HttpOperations


class DashboardTests(unittest.TestCase):
    def test_reject_non_tls_and_credential_urls(self):
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.dict("os.environ", {}, clear=True),
        ):
            file = Path(temp) / ".env"
            for url in (
                "http://remote.example",
                "https://user:secret@remote.example",
                "https://remote.example?key=secret",
            ):
                file.write_text("INSIDE_GAME_API_URL=" + url)
                with self.assertRaises(ValueError):
                    DashboardConfig.load(Path(temp))

    def test_load_new_key_without_restart(self):
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.dict("os.environ", {}, clear=True),
        ):
            file = Path(temp) / ".env"
            file.write_text(
                "INSIDE_GAME_API_URL=https://example.org\nINSIDE_GAME_API_KEY=first"
            )
            self.assertEqual(DashboardConfig.load(Path(temp)).api_key, "first")
            file.write_text(
                "INSIDE_GAME_API_URL=https://example.org\nINSIDE_GAME_API_KEY=second"
            )
            self.assertEqual(DashboardConfig.load(Path(temp)).api_key, "second")

    def test_no_arbitrary_operations(self):
        with self.assertRaises(DataError):
            HttpOperations(DashboardConfig("https://example.org", "")).execute(
                "execute_sql", {}
            )

    def test_reject_incomplete_frame(self):
        with self.assertRaises(DataError):
            EpisodeService._frame({"players": []}, {})

    def test_invalid_window_never_queries_upstream(self):
        class NeverCall:
            def execute(self, *_):
                raise AssertionError("Unexpected network access")

        with self.assertRaises(DataError):
            EpisodeService(NeverCall()).episode(1, 3, 0)

    def test_complete_episode_preserves_identities_and_does_not_interpolate(self):
        class FixtureOperations:
            def execute(self, operation, arguments):
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
                            "periods": [
                                {
                                    "period": 1,
                                    "run_id": "run",
                                    "duration_ms": 2000,
                                    "home_attacks_positive_x": True,
                                }
                            ],
                            "lineups": [
                                {
                                    "player_id": n,
                                    "player_name": f"P{n}",
                                    "jersey_number": (n - 1) % 11 + 1,
                                }
                                for n in range(1, 23)
                            ],
                        }
                    }
                if operation == "get_tracking_window":
                    players = [
                        {
                            "player_id": n,
                            "team_id": 1 if n <= 11 else 2,
                            "on_pitch_slot": (n - 1) % 11 + 1,
                            "is_on_pitch": True,
                            "position_status": "available",
                            "x_m": 5 + n * 3,
                            "y_m": 34,
                        }
                        for n in range(1, 23)
                    ]
                    return {
                        "data": {
                            "frames": [
                                {
                                    "period_time_ms": t,
                                    "players": players,
                                    "ball": None,
                                    "ball_in_play": True,
                                }
                                for t in (0, 1000)
                            ]
                        },
                        "warnings": ["Synthetic"],
                    }
                return {"data": {"items": []}}

        service = EpisodeService(FixtureOperations())
        episode = service.episode(1, 1, 0, duration_seconds=60, stride_s=1)
        self.assertEqual(len(episode["frames"]), 2)
        self.assertEqual(episode["frames"][0]["players"][11]["name"], "P12")
        self.assertTrue(episode["frames"][0]["players"][11]["goalkeeper"])
        self.assertIsNone(episode["frames"][0]["ball"])
        self.assertEqual(episode["source"], "azure")

    def test_incomplete_timeline_is_rejected(self):
        class GapOperations:
            def execute(self, operation, _):
                if operation == "get_match_context":
                    return {
                        "data": {
                            "match": {},
                            "periods": [
                                {
                                    "period": 1,
                                    "run_id": "run",
                                    "duration_ms": 60000,
                                    "home_attacks_positive_x": True,
                                }
                            ],
                            "lineups": [],
                        }
                    }
                return {"data": {"frames": [{"period_time_ms": 1000, "players": []}]}}

        with (
            patch.object(EpisodeService, "_frame", return_value={"timeMs": 1000}),
            self.assertRaisesRegex(DataError, "huecos"),
        ):
            EpisodeService(GapOperations()).episode(1, 1, 0)


if __name__ == "__main__":
    unittest.main()
