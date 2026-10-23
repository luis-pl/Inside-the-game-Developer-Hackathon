"""Deterministic definitions; no expressions or SQL originate in a request."""

from collections import Counter, defaultdict
from itertools import pairwise
from math import hypot

from inside_game.errors import DomainError

RESTARTS = {
    "corner": 61,
    "free_kick": 62,
    "goal_kick": 63,
    "kick_off": 65,
    "throw_in": 67,
}
ZONES = {
    "all": (0, 105, 0, 68),
    "defensive_third": (0, 35, 0, 68),
    "middle_third": (35, 70, 0, 68),
    "final_third": (70, 105, 0, 68),
    "penalty_area": (88.5, 105, 13.84, 54.16),
    "central_channel": (0, 105, 22.6666666667, 45.3333333333),
}
PROFILES = (
    "finishing",
    "chance_creation",
    "passing",
    "defending",
    "ball_progression",
    "movement",
    "set_pieces",
    "possession_sequences",
    "goalkeeping",
    "pressure_effectiveness",
    "ppda_demo",
)
EVENT_TYPES = {
    "shot": 16,
    "pass": 30,
    "pressure": 17,
    "dribble": 14,
    "carry": 43,
    "interception": 10,
}


def code(obj):
    return obj.get("id") if isinstance(obj, dict) else None


def ratio(a, b):
    return a / b if b else None


def in_scope(e, scope):
    return (scope.kind == "match" or e["period"] == scope.period) and (
        scope.kind != "window" or scope.start_ms <= e["period_time_ms"] < scope.end_ms
    )


def in_zone(x, y, zone):
    if x is None or y is None:
        return zone == "all"
    if zone == "defensive_third":
        return 0 <= x < 35 and 0 <= y <= 68
    if zone == "middle_third":
        return 35 <= x < 70 and 0 <= y <= 68
    a, b, c, d = ZONES[zone]
    return a <= x <= b and c <= y <= d


_AUTO = object()


def events_for(data, request, team=_AUTO, player=_AUTO):
    team = getattr(request, "team_id", None) if team is _AUTO else team
    player = getattr(request, "player_id", None) if player is _AUTO else player
    scores = {t["team_id"]: 0 for t in data["match_teams"]}
    rows = []
    for raw in data["events"]:
        e = {
            **raw,
            "pass": data["passes"].get(raw["event_id"]),
            "shot": data["shots"].get(raw["event_id"]),
        }
        e["attacking_x_m"] = (
            e["location_x"] * 105 / 120 if e["location_x"] is not None else None
        )
        e["attacking_y_m"] = (
            e["location_y"] * 68 / 80 if e["location_y"] is not None else None
        )
        state = "tied"
        if e["team_id"] in scores:
            own = scores[e["team_id"]]
            other = next(v for k, v in scores.items() if k != e["team_id"])
            state = "leading" if own > other else "trailing" if own < other else "tied"
        e["score_state_before"] = state
        if e["shot"] and code(e["shot"]["outcome"]) == 97:
            scores[e["team_id"]] += 1
        if (
            team is not None
            and e["team_id"] != team
            or player is not None
            and e["player_id"] != player
        ):
            continue
        if not in_scope(e, request.scope):
            continue
        if not in_zone(
            e["attacking_x_m"], e["attacking_y_m"], getattr(request, "zone_id", "all")
        ):
            continue
        if getattr(request, "score_state", "all") not in ("all", state):
            continue
        pressure = getattr(request, "pressure", "all")
        if (
            pressure == "under_pressure"
            and not e["under_pressure"]
            or pressure == "unpressured"
            and e["under_pressure"]
        ):
            continue
        rows.append(e)
    return rows


def defensive_kind(e):
    if e["type_id"] == 4:
        return (
            "aerial_duel"
            if code(e["details"].get("duel", {}).get("type")) == 10
            else "tackle"
        )
    return {
        2: "recovery",
        6: "block",
        9: "clearance",
        10: "interception",
        17: "pressure",
        23: "goalkeeper",
        33: "fifty_fifty",
    }.get(e["type_id"])


def won_lost(e):
    if e["type_id"] == 4:
        d = e["details"].get("duel", {})
        if code(d.get("type")) == 10:
            return "lost"
        return "won" if code(d.get("outcome")) in (4, 16, 17) else "lost"
    if e["type_id"] == 33:
        return (
            "won" if code(e["details"].get("50_50", {}).get("outcome")) == 3 else "lost"
        )
    if e["type_id"] == 9 and e["details"].get("clearance", {}).get("aerial_won"):
        return "won"
    return None


def aerial_contests(data, rows):
    selected = {e["event_id"]: e for e in rows}
    result = []
    for r in data["event_relations"]:
        loser, winner = (
            data["event_index"][r["event_id"]],
            data["event_index"][r["related_event_id"]],
        )
        if (
            loser["type_id"] != 4
            or code(loser["details"].get("duel", {}).get("type")) != 10
            or not winner["details"].get("clearance", {}).get("aerial_won")
        ):
            continue
        selected_event = selected.get(loser["event_id"]) or selected.get(
            winner["event_id"]
        )
        if selected_event:
            both = winner["event_id"] in selected and loser["event_id"] in selected
            result.append(
                {
                    **selected_event,
                    "contest_id": loser["event_id"],
                    "winner": {
                        "team_id": winner["team_id"],
                        "player_id": winner["player_id"],
                        "event_id": winner["event_id"],
                    },
                    "loser": {
                        "team_id": loser["team_id"],
                        "player_id": loser["player_id"],
                        "event_id": loser["event_id"],
                    },
                    "outcome": "both"
                    if both
                    else "won"
                    if selected_event["event_id"] == winner["event_id"]
                    else "lost",
                }
            )
    return result


def possession_rows(rows):
    groups = defaultdict(list)
    for e in rows:
        if e["possession"] is not None:
            groups[(e["match_id"], e["possession"])].append(e)
    return [
        {
            "match_id": match,
            "possession": poss,
            "team_id": es[0]["possession_team_id"],
            "period": es[0]["period"],
            "start_ms": min(e["period_time_ms"] for e in es),
            "end_ms": max(e["period_time_ms"] for e in es),
            "recorded_span_seconds": (
                max(e["period_time_ms"] for e in es)
                - min(e["period_time_ms"] for e in es)
            )
            / 1000,
            "passes": sum(e["type_id"] == 30 for e in es),
            "shots": sum(e["type_id"] == 16 for e in es),
            "xg": sum(e["shot"]["statsbomb_xg"] or 0 for e in es if e["shot"]),
            "event_ids": [e["event_id"] for e in es],
        }
        for (match, poss), es in groups.items()
    ]


def sequence_rows(data, rows, pattern, scope=None):
    all_events = data["events"]
    result = []
    if pattern == "pass_aba":
        selected = {e["event_id"] for e in rows}
        passes = [e for e in all_events if e["event_id"] in data["passes"]]
        for a, b in pairwise(passes):
            pa, pb = data["passes"][a["event_id"]], data["passes"][b["event_id"]]
            if (
                a["event_id"] in selected
                and (scope is None or in_scope(b, scope))
                and a["period"] == b["period"]
                and a["possession"] == b["possession"]
                and a["team_id"] == b["team_id"]
                and pa["outcome"] is None
                and pb["outcome"] is None
                and pa["recipient_player_id"] == b["player_id"]
                and pb["recipient_player_id"] == a["player_id"]
            ):
                result.append(
                    {
                        "pattern_id": pattern,
                        "period": a["period"],
                        "start_ms": a["period_time_ms"],
                        "end_ms": b["period_time_ms"],
                        "event_ids": [a["event_id"], b["event_id"]],
                    }
                )
        return result
    seen_episodes = set()
    for a in rows:
        recovered = (
            a["type_id"] in (2, 10) or a["type_id"] in (4, 33) and won_lost(a) == "won"
        )
        is_anchor = (
            (pattern == "after_dribble" and a["type_id"] == 14)
            or (pattern == "turnover_to_shot" and recovered)
            or (pattern == "pressure_to_recovery" and a["type_id"] == 17)
        )
        if not is_anchor:
            continue
        seconds = (
            5
            if pattern == "pressure_to_recovery"
            else 60
            if pattern == "turnover_to_shot"
            else 10
        )
        episode = a["possession"]
        if pattern == "turnover_to_shot":
            first = next(
                (
                    b
                    for b in all_events
                    if b["event_index"] >= a["event_index"]
                    and b["period"] == a["period"]
                    and b["team_id"] == a["team_id"]
                    and b["possession_team_id"] == a["team_id"]
                    and b["possession"] is not None
                    and b["type_id"] in (2, 16, 30, 43)
                    and 0 <= b["period_time_ms"] - a["period_time_ms"] <= 10000
                ),
                None,
            )
            if first is None:
                continue
            episode = first["possession"]
            if (a["period"], episode) in seen_episodes:
                continue
            seen_episodes.add((a["period"], episode))
        for b in all_events:
            if (
                b["match_id"] != a["match_id"]
                or b["period"] != a["period"]
                or b["event_index"] <= a["event_index"]
                or not 0 <= b["period_time_ms"] - a["period_time_ms"] <= seconds * 1000
            ):
                continue
            if b["team_id"] != a["team_id"]:
                continue
            if scope is not None and not in_scope(b, scope):
                continue
            match = (
                (
                    pattern == "after_dribble"
                    and b["possession"] == a["possession"]
                    and b["player_id"] == a["player_id"]
                    and b["type_id"] in (3, 16, 30, 38)
                )
                or (
                    pattern == "turnover_to_shot"
                    and b["type_id"] == 16
                    and b["possession"] == episode
                )
                or (
                    pattern == "pressure_to_recovery"
                    and (
                        b["type_id"] in (2, 10)
                        or b["type_id"] in (4, 33)
                        and won_lost(b) == "won"
                    )
                )
            )
            if match:
                result.append(
                    {
                        "pattern_id": pattern,
                        "period": a["period"],
                        "start_ms": a["period_time_ms"],
                        "end_ms": b["period_time_ms"],
                        "team_id": a["team_id"],
                        "event_ids": [a["event_id"], b["event_id"]],
                    }
                )
                break
    return result


def summary(data, rows, profile, minutes=None, team=None, scope=None):
    passes, shots = [e for e in rows if e["pass"]], [e for e in rows if e["shot"]]
    complete = [e for e in passes if e["pass"]["outcome"] is None]
    goals = sum(code(e["shot"]["outcome"]) == 97 for e in shots)
    xg = sum(e["shot"]["statsbomb_xg"] or 0 for e in shots)
    if profile == "finishing":
        on_target = sum(code(e["shot"]["outcome"]) in (97, 100, 116) for e in shots)
        return {
            "shots": len(shots),
            "goals": goals,
            "shots_on_target": on_target,
            "xg": xg,
            "xg_per_shot": ratio(xg, len(shots)),
            "goals_minus_xg": goals - xg,
            "conversion_rate": ratio(goals, len(shots)),
            "on_target_rate": ratio(on_target, len(shots)),
            "outcomes": dict(Counter(e["shot"]["outcome"]["name"] for e in shots)),
            "body_parts": dict(Counter(e["shot"]["body_part"]["name"] for e in shots)),
        }
    if profile == "chance_creation":
        shot_index = defaultdict(list)
        for s in data["event_shots"]:
            if s["key_pass_id"]:
                shot_index[s["key_pass_id"]].append(s)
        return {
            "key_passes": sum(bool(e["pass"]["shot_assist"]) for e in passes),
            "assists": sum(bool(e["pass"]["goal_assist"]) for e in passes),
            "assisted_shot_xg": sum(
                s["statsbomb_xg"] or 0
                for e in passes
                for s in shot_index[e["event_id"]]
            ),
            "definition": "Sum xG of shots linked by key_pass_id; toy xG.",
        }
    if profile == "passing":
        lengths, progressive, entries = [], 0, 0
        for e in passes:
            p = e["pass"]
            x, y, ex, ey = (
                e["attacking_x_m"],
                e["attacking_y_m"],
                p["end_x"] * 105 / 120,
                p["end_y"] * 68 / 80,
            )
            lengths.append(hypot(ex - x, ey - y))
            progressive += (
                p["outcome"] is None
                and hypot(105 - x, 34 - y) - hypot(105 - ex, 34 - ey) >= 10
            )
            entries += p["outcome"] is None and x < 70 <= ex
        return {
            "attempted_passes": len(passes),
            "completed_passes": len(complete),
            "completion_rate": ratio(len(complete), len(passes)),
            "total_pass_length_m": sum(lengths),
            "progressive_passes": progressive,
            "final_third_entries": entries,
            **{
                k: sum(bool(e["pass"][k]) for e in passes)
                for k in ("cross", "cut_back", "switch")
            },
        }
    if profile == "defending":
        tackles = [e for e in rows if defensive_kind(e) == "tackle"]
        aerial = [e for e in rows if "contest_id" in e] or aerial_contests(data, rows)
        return {
            "tackle_attempts": len(tackles),
            "tackles_won": sum(won_lost(e) == "won" for e in tackles),
            "tackles_lost": sum(won_lost(e) == "lost" for e in tackles),
            "aerial_contests": len(aerial),
            "aerial_won": sum(e["outcome"] in ("won", "both") for e in aerial),
            "aerial_lost": sum(e["outcome"] in ("lost", "both") for e in aerial),
            "fifty_fifty_winning_records": sum(
                e["type_id"] == 33 and won_lost(e) == "won" for e in rows
            ),
            "fifty_fifty_losing_records": sum(
                e["type_id"] == 33 and won_lost(e) == "lost" for e in rows
            ),
            **{
                name: sum(e["type_id"] == id for e in rows)
                for name, id in {
                    "interceptions": 10,
                    "pressures": 17,
                    "blocks": 6,
                    "clearances": 9,
                    "recoveries": 2,
                    "fouls_committed": 22,
                }.items()
            },
            "counterpressures": sum(
                e["type_id"] == 17 and bool(e["counterpress"]) for e in rows
            ),
        }
    if profile == "ball_progression":
        dribbles = [e for e in rows if e["type_id"] == 14]
        won = sum(
            code(e["details"].get("dribble", {}).get("outcome")) == 8 for e in dribbles
        )
        carries = [e for e in rows if e["type_id"] == 43]
        return {
            "dribble_attempts": len(dribbles),
            "dribbles_complete": won,
            "dribbles_incomplete": len(dribbles) - won,
            "dribble_success_rate": ratio(won, len(dribbles)),
            "carries": len(carries),
            "carry_seconds": sum(e["duration"] or 0 for e in carries),
            "carry_displacement_m": sum(
                hypot(
                    e["details"]["carry"]["end_location"][0] * 105 / 120
                    - e["attacking_x_m"],
                    e["details"]["carry"]["end_location"][1] * 68 / 80
                    - e["attacking_y_m"],
                )
                for e in carries
            ),
            "carry_progression_m": sum(
                e["details"]["carry"]["end_location"][0] * 105 / 120
                - e["attacking_x_m"]
                for e in carries
            ),
            "miscontrols": sum(e["type_id"] == 38 for e in rows),
            "dispossessed": sum(e["type_id"] == 3 for e in rows),
            "receipts": sum(e["type_id"] == 42 for e in rows),
        }
    if profile == "goalkeeping":
        saves = [
            e
            for e in rows
            if e["type_id"] == 23
            and code(e["details"].get("goalkeeper", {}).get("type")) == 33
        ]
        return {
            "saves": len(saves),
            "goalkeeper_events": sum(e["type_id"] == 23 for e in rows),
            "save_event_ids": [e["event_id"] for e in saves],
        }
    if profile == "set_pieces":
        return {
            "restarts": dict(
                Counter(
                    e["pass"]["pass_type"]["name"]
                    for e in passes
                    if e["pass"]["pass_type"]
                )
            )
        }
    if profile == "possession_sequences":
        groups = possession_rows(rows)
        return {
            "recorded_possessions": len(groups),
            "with_shot": sum(g["shots"] > 0 for g in groups),
            "total_recorded_span_seconds": sum(
                g["recorded_span_seconds"] for g in groups
            ),
            "duration_method": "first-to-last selected event, not exact possession time",
        }
    if profile == "pressure_effectiveness":
        pressures = [e for e in rows if e["type_id"] == 17]
        durations = []
        for p in pressures:
            cap = next(
                int(x["duration_ms"])
                for x in data["tracking_periods"]
                if x["period"] == p["period"]
            )
            if scope is not None and scope.kind == "window":
                cap = min(cap, scope.end_ms)
            durations.append(
                (
                    p["period"],
                    p["period_time_ms"],
                    min(cap, p["period_time_ms"] + int((p["duration"] or 0) * 1000)),
                )
            )
        merged, union = {}, 0
        for period, start, end in sorted(durations):
            old = merged.get(period)
            if old is None or start > old[1]:
                if old:
                    union += old[1] - old[0]
                merged[period] = [start, end]
            else:
                old[1] = max(old[1], end)
        union += sum(b - a for a, b in merged.values())
        eligible = []
        for p in pressures:
            cap = next(
                int(x["duration_ms"])
                for x in data["tracking_periods"]
                if x["period"] == p["period"]
            )
            if scope is not None and scope.kind == "window":
                cap = min(cap, scope.end_ms)
            if p["period_time_ms"] + 5000 < cap:
                eligible.append(p)
        pairs = sequence_rows(data, eligible, "pressure_to_recovery", scope)
        return {
            "pressures": len(pressures),
            "summed_action_seconds": sum(max(0, b - a) for _, a, b in durations) / 1000,
            "union_pressure_seconds": union / 1000,
            "eligible_pressures": len(eligible),
            "censored_pressures": len(pressures) - len(eligible),
            "pressures_followed_by_recovery_within_5s": len(pairs),
            "association_rate": ratio(len(pairs), len(eligible)),
            "causal": False,
        }
    if profile == "movement":
        return {"minutes": minutes}
    if profile == "ppda_demo":
        if team is None:
            raise DomainError("UNSUPPORTED_METRIC", "ppda_demo is a team metric.")
        denominator = sum(
            (e["type_id"] in (10, 22) or defensive_kind(e) == "tackle")
            and (e["attacking_x_m"] or 0) >= 42
            for e in rows
            if e["team_id"] == team
        )
        numerator = sum(
            e["pass"] is not None
            and e["pass"]["pass_type"] is None
            and e["attacking_x_m"] <= 63
            for e in rows
            if e["team_id"] != team
        )
        return {
            "ppda_demo": ratio(numerator, denominator),
            "opponent_regular_pass_attempts_own_60_percent": numerator,
            "defensive_actions_opponent_60_percent": denominator,
            "definition": "Opponent regular pass attempts at attacking x<=63m / own tackles+interceptions+fouls at attacking x>=42m. Demo definition.",
        }
    raise DomainError("UNSUPPORTED_METRIC", "Metric profile is not supported.")
