from uuid import UUID

import pytest


def uid(n):
    return str(UUID(int=n))


def fixture_match():
    rows = []

    def event(
        n,
        type,
        team=1,
        player=110,
        t=1000,
        period=1,
        details=None,
        duration=0,
        possession=1,
    ):
        e = {
            "event_id": uid(n),
            "match_id": 900001,
            "event_index": n,
            "period": period,
            "period_time_ms": t,
            "type_id": type,
            "type_name": {16: "Shot", 30: "Pass", 17: "Pressure"}.get(type, str(type)),
            "team_id": team,
            "player_id": player,
            "possession": possession,
            "possession_team_id": 1 if possession == 1 else 2,
            "location_x": 60.0,
            "location_y": 40.0,
            "duration": duration,
            "details": details or {},
            "under_pressure": False,
            "counterpress": False,
            "position_id": 13,
            "position_name": "Center Midfield",
            "play_pattern_id": 1,
        }
        rows.append(e)
        return e

    event(1, 30, duration=1)
    event(2, 16, player=106, t=3000, duration=2)
    event(3, 17, team=2, player=206, t=4000, duration=2)
    event(
        4,
        10,
        team=2,
        player=210,
        t=5000,
        details={"interception": {"outcome": {"id": 16}}},
    )
    event(5, 2, team=2, player=210, t=6000, possession=2)
    event(6, 22, player=106, t=10000, possession=2)
    event(7, 21, team=2, player=210, t=10000, possession=2)
    event(8, 4, t=12000, details={"duel": {"type": {"id": 10, "name": "Aerial Lost"}}})
    event(
        9, 9, team=2, player=210, t=12000, details={"clearance": {"aerial_won": True}}
    )
    event(10, 14, t=20000, details={"dribble": {"outcome": {"id": 8}}})
    event(11, 39, team=2, player=206, t=20000)
    event(
        12,
        4,
        team=2,
        player=206,
        t=20000,
        details={"duel": {"type": {"id": 11}, "outcome": {"id": 13}}},
    )
    event(13, 14, player=106, t=25000, details={"dribble": {"outcome": {"id": 9}}})
    event(14, 3, player=106, t=25000)
    event(
        15,
        4,
        team=2,
        player=210,
        t=25000,
        details={"duel": {"type": {"id": 11}, "outcome": {"id": 4}}},
    )
    event(16, 33, t=30000, details={"50_50": {"outcome": {"id": 3}}})
    event(
        17, 33, team=2, player=210, t=30000, details={"50_50": {"outcome": {"id": 1}}}
    )
    event(18, 16, t=35000, duration=2)
    event(
        19,
        23,
        team=2,
        player=201,
        t=37000,
        details={"goalkeeper": {"type": {"id": 33}}},
    )
    event(
        20, 43, t=40000, duration=2, details={"carry": {"end_location": [62.0, 40.0]}}
    )
    event(21, 38, t=42000)
    event(
        22,
        19,
        player=106,
        t=9000,
        period=2,
        details={"substitution": {"replacement": {"id": 112}, "outcome": {"id": 103}}},
    )
    passes = [
        {
            "event_id": uid(1),
            "recipient_player_id": 106,
            "outcome": None,
            "height": {"id": 1},
            "pass_type": None,
            "end_x": 80.0,
            "end_y": 40.0,
            "shot_assist": True,
            "goal_assist": True,
            "cross": False,
            "switch": False,
            "cut_back": False,
        }
    ]
    shots = [
        {
            "event_id": uid(n),
            "key_pass_id": uid(1) if n == 2 else None,
            "outcome": {"id": outcome, "name": name},
            "body_part": {"id": 40, "name": "Right Foot"},
            "statsbomb_xg": xg,
            "end_x": 120.0,
            "end_y": 40.0,
            "end_z": 1.0,
        }
        for n, outcome, name, xg in [(2, 97, "Goal", 0.2), (18, 100, "Saved", 0.3)]
    ]
    lineups = [
        {"match_id": 900001, "team_id": team, "player_id": p, "jersey_number": p % 100}
        for team, ps in [(1, [101, 106, 110, 112]), (2, [201, 206, 210])]
        for p in ps
    ]
    intervals = [
        {
            "player_id": p["player_id"],
            "team_id": p["team_id"],
            "position_id": 1 if p["player_id"] % 100 == 1 else 13,
            "from_time": "01:10" if p["player_id"] == 112 else "00:00",
            "to_time": "01:10" if p["player_id"] == 106 else "02:00",
        }
        for p in lineups
    ]
    run = {
        "run_id": uid(999),
        "match_id": 900001,
        "pitch_length_m": 105.0,
        "pitch_width_m": 68.0,
        "sample_rate_hz": 1,
        "generator_version": "3.0.0",
        "is_synthetic": True,
    }
    data = {
        "meta": {
            "match_id": 900001,
            "generator_version": "3.0.0",
            "is_synthetic": True,
        },
        "revision": "fixture-revision",
        "matches": [{"match_id": 900001}],
        "match_teams": [{"team_id": 1, "side": "home"}, {"team_id": 2, "side": "away"}],
        "match_lineups": lineups,
        "lineup_positions": intervals,
        "lineup_cards": [],
        "events": rows,
        "event_passes": passes,
        "event_shots": shots,
        "event_relations": [
            {"event_id": uid(a), "related_event_id": uid(b)}
            for a, b in [(1, 2), (8, 9), (10, 11), (12, 10), (16, 17), (18, 19)]
        ],
        "tracking_runs": [run],
        "tracking_periods": [
            {
                "period": p,
                "run_id": uid(999),
                "duration_ms": 60000,
                "home_attacks_positive_x": p == 1,
            }
            for p in (1, 2)
        ],
        "event_tactics": [],
        "tactical_lineups": [],
        "frames_360": [],
        "shot_freeze_players": [],
        "frame_360_players": [],
        "event_tracking_links": [
            {
                "event_id": e["event_id"],
                "run_id": uid(999),
                "period": e["period"],
                "frame_index": e["period_time_ms"] // 1000,
            }
            for e in rows
        ],
    }
    data["passes"] = {p["event_id"]: p for p in passes}
    data["shots"] = {p["event_id"]: p for p in shots}
    data["event_index"] = {e["event_id"]: e for e in rows}
    return data


class FixtureRepository:
    def __init__(self):
        self.data = fixture_match()

    def match(self, match_id):
        from inside_game.errors import DomainError

        if match_id != 900001:
            raise DomainError("MATCH_NOT_FOUND", "Unavailable", 404)
        return self.data

    def catalog(self):
        return {
            "matches": [
                {
                    "match_id": 900001,
                    "home_team_id": 1,
                    "away_team_id": 2,
                    "match_date": "2026-10-01",
                    "is_synthetic": True,
                }
            ],
            "teams": [
                {"team_id": 1, "team_name": "One"},
                {"team_id": 2, "team_name": "Two"},
            ],
            "players": [{"player_id": 110, "player_name": "Player One"}],
        }

    def event_match(self, event_id):
        return self.data

    def tracking(
        self, match, run, period, start, end, stride=1, team=None, player=None
    ):
        frames = []
        for t in range(start, end, stride * 1000):
            coords = [
                (101, 1, 10, 34, 1),
                (106 if period == 1 or t < 10000 else 112, 1, 40, 10, 6),
                (110, 1, 60, 50, 10),
                (201, 2, 95, 34, 1),
                (206, 2, 70, 12, 6),
                (210, 2, 50, 48, 10),
            ]
            ps = [
                {
                    "player_id": id,
                    "team_id": s,
                    "x_m": float(x),
                    "y_m": float(y),
                    "is_on_pitch": True,
                    "position_status": "available",
                    "on_pitch_slot": slot,
                }
                for id, s, x, y, slot in coords
                if (team is None or s == team) and (player is None or id == player)
            ]
            frames.append(
                {
                    "period": period,
                    "frame_index": t // 1000,
                    "period_time_ms": t,
                    "ball_in_play": True,
                    "players": ps,
                    "ball": {
                        "x_m": 60.0,
                        "y_m": 50.0,
                        "z_m": 0.0,
                        "position_status": "available",
                    },
                }
            )
        return frames

    def anchor_tracking(self, run, ids):
        return [
            self.tracking(
                900001,
                run,
                self.data["event_index"][id]["period"],
                self.data["event_index"][id]["period_time_ms"],
                self.data["event_index"][id]["period_time_ms"] + 1,
            )[0]
            for id in ids
        ]


@pytest.fixture
def repository():
    return FixtureRepository()
