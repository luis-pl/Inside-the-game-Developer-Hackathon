"""Five-minute loading respects upstream caps and sampled chronology."""
import unittest
from unittest.mock import patch

from inside_game.dashboard.gateway import DataError, EpisodeService


class TrackingFixture:
    def __init__(self, duration=2700000, corrupt=False):
        self.duration = duration
        self.corrupt = corrupt
        self.calls = []

    def execute(self, operation, arguments):
        self.calls.append((operation, arguments))
        if operation == "get_match_context":
            return {"data": {
                "match": {"match_id": 1, "home_team_id": 1, "away_team_id": 2,
                          "home_team_name": "A", "away_team_name": "B"},
                "lineups": [],
                "periods": [{"period": 1, "run_id": "run", "duration_ms": self.duration,
                             "home_attacks_positive_x": True}],
            }}
        if operation == "get_tracking_window":
            scope = arguments["scope"]
            times = list(range(scope["start_ms"], scope["end_ms"], arguments["stride_s"] * 1000))
            if self.corrupt and scope["start_ms"] > 600000:
                times[0] -= 5000
            return {"data": {"frames": [{"timeMs": t} for t in times]}, "warnings": ["Synthetic"]}
        return {"data": {"items": []}}


class LongReplayTests(unittest.TestCase):
    def load(self, fixture, start=600):
        with patch.object(EpisodeService, "_frame", side_effect=lambda frame, _: frame):
            return EpisodeService(fixture).episode(1, 1, start, duration_seconds=300)

    def test_five_minutes_load_in_three_bounded_calls(self):
        fixture = TrackingFixture()
        result = self.load(fixture)
        self.assertEqual([f["timeMs"] for f in result["frames"]], list(range(600000, 900000, 1000)))
        calls = [a for op, a in fixture.calls if op == "get_tracking_window"]
        self.assertEqual([(a["scope"]["start_ms"], a["scope"]["end_ms"]) for a in calls],
                         [(600000,720000),(720000,840000),(840000,900000)])
        self.assertTrue(all(a["stride_s"] == 1 for a in calls))
        self.assertEqual(result["window"], {"startMs":600000,"endMs":900000,"sampleStepMs":1000})
        self.assertEqual(result["warnings"], ["Synthetic"])
        for operation, arguments in fixture.calls:
            if operation in ("get_events", "get_passes"):
                self.assertEqual(arguments["scope"]["end_ms"],900000)

    def test_end_is_clipped_to_period_without_crossing_halftime(self):
        fixture = TrackingFixture(duration=747000)
        result = self.load(fixture)
        self.assertEqual(result["window"]["endMs"],747000)
        self.assertEqual(result["frames"][-1]["timeMs"],746000)
        self.assertEqual(len(result["frames"]),147)

    def test_chunk_duplicates_fail_instead_of_silently_filling_gaps(self):
        with self.assertRaisesRegex(DataError,"huecos"):
            self.load(TrackingFixture(corrupt=True))

    def test_non_round_start_keeps_one_sampling_phase(self):
        result = self.load(TrackingFixture(),start=603)
        self.assertEqual([f["timeMs"] for f in result["frames"]],list(range(603000,903000,1000)))

    def test_default_loads_complete_45_minute_period(self):
        fixture = TrackingFixture()
        with patch.object(EpisodeService, "_frame", side_effect=lambda frame,_:frame):
            result=EpisodeService(fixture).episode(1,1,0)
        self.assertEqual(len(result["frames"]),2700)
        self.assertEqual(result["frames"][0]["timeMs"],0)
        self.assertEqual(result["frames"][-1]["timeMs"],2699000)
        calls=[a for op,a in fixture.calls if op=="get_tracking_window"]
        self.assertEqual(len(calls),23)
        self.assertTrue(all(a["scope"]["end_ms"]-a["scope"]["start_ms"]<=120000 for a in calls))

    def test_all_event_pages_are_loaded_and_duplicates_are_rejected(self):
        class Pages:
            def execute(self,operation,arguments):
                index=1 if "cursor" not in arguments else 2
                return {"data":{"items":[{"event_id":str(index),"period_time_ms":index*1000,"type_name":"Pass"}]},"pagination":{"next_cursor":"second" if index==1 else None}}
        result=EpisodeService(Pages())._events(1,1,0,2700000)
        self.assertEqual([e["timeMs"] for e in result],[1000,2000])
        class Repeat:
            def execute(self,*_):
                return {"data":{"items":[{"event_id":"same","period_time_ms":0,"type_name":"Pass"}]},"pagination":{"next_cursor":"again"}}
        with self.assertRaisesRegex(DataError,"repitió"):
            EpisodeService(Repeat())._events(1,1,0,2700000)


if __name__ == "__main__":
    unittest.main()
