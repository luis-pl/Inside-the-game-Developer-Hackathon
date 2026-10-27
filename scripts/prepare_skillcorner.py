"""Prepare real SkillCorner tracking, keeping provider detection provenance.

Names, birthdays and original player/team identifiers never enter the prepared
database rows. Public match provenance remains traceable: this is pseudonymized
open data, not a claim of irreversible anonymization.
"""

import bisect
import csv
import gzip
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from prepare_metrica import TEAM_NAMES, clock, lineup_clock, number

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache/skillcorner"
VERSION = "skillcorner-pseudonymized-1.0.0"
STEP = 200


def prepare(game, source_id, manifest):
    mid = 900100 + game
    uid = lambda value: str(
        uuid5(NAMESPACE_URL, f"inside-game/skillcorner/{VERSION}/{source_id}/{value}")
    )
    run = uid("run")
    meta = json.loads((CACHE / f"{source_id}_match.json").read_text(encoding="utf-8"))
    length, width = float(meta["pitch_length"]), float(meta["pitch_width"])
    sx, sy = 105 / length, 68 / width
    fixed = lambda x, y: (
        None
        if x is None or y is None
        else ((x + length / 2) * sx, (width / 2 - y) * sy)
    )
    teams = [200 + game * 2, 201 + game * 2]
    original_teams = [meta["home_team"]["id"], meta["away_team"]["id"]]
    players = sorted(meta["players"], key=lambda p: p["id"])
    pids = {p["id"]: 10000 + game * 100 + i + 1 for i, p in enumerate(players)}
    pmeta = {p["id"]: p for p in players}
    payload = lambda **extra: {
        "is_synthetic": False,
        "data_kind": "real_pseudonymized",
        "provider": "SkillCorner",
        "version": VERSION,
        "source_url": manifest["repository"],
        "source_revision": manifest["revision"],
        "source_match_id": source_id,
        **extra,
    }
    periods = {
        int(p["period"]): {
            **p,
            "duration_ms": int(p["duration_frames"]) * 100,
            "home_positive": meta["home_team_side"][int(p["period"]) - 1]
            == "left_to_right",
        }
        for p in meta["match_periods"]
        if int(p["period"]) in (1, 2)
    }
    offset = 0
    for p in sorted(periods):
        periods[p]["offset_ms"] = offset
        offset += periods[p]["duration_ms"]
    # Authoritative participation intervals; no invented formation.
    spans = {}
    for player in players:
        for span in (player.get("playing_time") or {}).get("by_period", []):
            period = int(span["name"].split("_")[-1])
            if period not in periods:
                continue
            a, b = int(span["start_frame"]), int(span["end_frame"])
            if b < a:
                continue
            spans[(period, player["id"])] = {
                "a": a,
                "b": b,
                "side": original_teams.index(player["team_id"]),
            }
    for period, pd in periods.items():
        for side in (0, 1):
            assigned = []
            active = sorted(
                [
                    (key, s)
                    for key, s in spans.items()
                    if key[0] == period and s["side"] == side
                ],
                key=lambda item: (
                    item[1]["a"],
                    pmeta[item[0][1]]["player_role"]["name"] != "Goalkeeper",
                    item[0][1],
                ),
            )
            for key, span in active:
                used = {s["slot"] for s in assigned if s["b"] >= span["a"]}
                keeper = pmeta[key[1]]["player_role"]["name"] == "Goalkeeper"
                options = [1] if keeper else list(range(2, 12))
                free = [slot for slot in options if slot not in used]
                assert free, (
                    f"Overlapping source intervals exceed capacity: {source_id}/{period}/{side}"
                )
                span["slot"] = free[0]
                assigned.append(span)
    tables = defaultdict(list)
    for side in (0, 1):
        tables["teams"].append(
            {
                "team_id": teams[side],
                "team_name": TEAM_NAMES[teams[side]],
            }
        )
        tables["match_teams"].append(
            {
                "match_id": mid,
                "team_id": teams[side],
                "side": "home" if side == 0 else "away",
                "lineup_raw_payload": payload(),
            }
        )
    for player in players:
        pid = pids[player["id"]]
        side = original_teams.index(player["team_id"])
        name = f"SC{game:02} Jugador {pid % 100:02}"
        tables["players"].append({"player_id": pid, "player_name": name})
        tables["match_lineups"].append(
            {
                "match_id": mid,
                "team_id": teams[side],
                "player_id": pid,
                "jersey_number": int(player["number"]),
                "raw_payload": payload(),
            }
        )
        for period, pd in periods.items():
            span = spans.get((period, player["id"]))
            if not span:
                continue
            a = max(0, (span["a"] - pd["start_frame"]) * 100)
            b = min(pd["duration_ms"], (span["b"] - pd["start_frame"] + 1) * 100)
            tables["lineup_positions"].append(
                {
                    "match_id": mid,
                    "team_id": teams[side],
                    "player_id": pid,
                    "position_index": period - 1,
                    "position_id": 1 if span["slot"] == 1 else None,
                    "position": player["player_role"]["name"],
                    "from_time": lineup_clock(pd["offset_ms"] + a),
                    "to_time": lineup_clock(pd["offset_ms"] + b),
                    "from_period": period,
                    "to_period": period,
                    "start_reason": "Provider participation interval",
                    "end_reason": "Provider participation interval",
                }
            )
    raw_events = list(
        csv.DictReader(
            (CACHE / f"{source_id}_dynamic_events.csv").open(
                encoding="utf-8", newline=""
            )
        )
    )
    possessions = [
        r
        for r in raw_events
        if r["event_type"] == "player_possession" and int(r["period"]) in periods
    ]
    receptions = defaultdict(list)
    for r in possessions:
        receptions[(int(r["period"]), int(r["player_id"]))].append(
            int(r["frame_start"])
        )
    for values in receptions.values():
        values.sort()
    possession = 0
    previous_side = None
    for index, row in enumerate(raw_events):
        period = int(row["period"])
        if period not in periods:
            continue
        original_pid = int(row["player_id"])
        if original_pid not in pids:
            continue
        pd = periods[period]
        side = original_teams.index(int(row["team_id"]))
        is_possession = row["event_type"] == "player_possession"
        source_frame = int(row["frame_end"] if is_possession else row["frame_start"])
        ms = (source_frame - int(pd["start_frame"])) * 100
        if not 0 <= ms <= pd["duration_ms"]:
            continue
        if is_possession and side != previous_side:
            possession += 1
            previous_side = side
        kind = row["end_type"] if is_possession else row["event_type"]
        code, name = (
            (30, "Pass")
            if kind == "pass"
            else (16, "Shot")
            if kind == "shot"
            else (21, "Foul Won")
            if kind == "foul_suffered"
            else (1100, "SkillCorner " + row["event_type"])
        )
        xy = fixed(
            number(row["x_end" if is_possession else "x_start"]),
            number(row["y_end" if is_possession else "y_start"]),
        )
        positive = pd["home_positive"] == (side == 0)
        oriented = lambda point, positive=positive: (
            None
            if point is None
            else (point[0] * 120 / 105, point[1] * 80 / 68)
            if positive
            else ((105 - point[0]) * 120 / 105, (68 - point[1]) * 80 / 68)
        )
        loc = oriented(xy)
        eid = uid("event/" + row["event_id"])
        details = {
            "skillcorner": {
                "type": row["event_type"],
                "end_type": row["end_type"],
                "source_event_id": row["event_id"],
            }
        }
        if kind == "foul_suffered":
            details["foul_won"] = {}
        event = {
            "event_id": eid,
            "match_id": mid,
            "period": period,
            "timestamp": clock(ms),
            "minute": (period - 1) * 45 + ms // 60000,
            "second": ms // 1000 % 60,
            "type_id": code,
            "type_name": name,
            "team_id": teams[side],
            "player_id": pids[original_pid],
            "location_x": loc[0] if loc else None,
            "location_y": loc[1] if loc else None,
            "duration": 0
            if is_possession
            else max(0, (int(row["frame_end"]) - int(row["frame_start"])) / 10),
            "possession": possession if is_possession else None,
            "possession_team_id": teams[side] if is_possession else None,
            "details": details,
            "raw_payload": payload(
                source_event_id=row["event_id"], source_frame=source_frame
            ),
            "_ms": ms,
        }
        tables["events"].append(event)
        if code == 30:
            target = (
                int(row["player_targeted_id"]) if row["player_targeted_id"] else None
            )
            success = row["pass_outcome"] == "successful"
            end = (
                oriented(
                    fixed(
                        number(row["player_targeted_x_reception"]),
                        number(row["player_targeted_y_reception"]),
                    )
                )
                if success
                else None
            )
            times = receptions.get((period, target), [])
            ri = bisect.bisect_right(times, source_frame)
            arrival = (
                times[ri]
                if success and ri < len(times) and times[ri] - source_frame <= 100
                else None
            )
            event["duration"] = (
                (arrival - source_frame) / 10 if arrival is not None else None
            )
            high = (
                True
                if row["high_pass"] == "True"
                else False
                if row["high_pass"] == "False"
                else None
            )
            tables["event_passes"].append(
                {
                    "event_id": eid,
                    "event_type_id": 30,
                    "match_id": mid,
                    "team_id": teams[side],
                    "recipient_player_id": pids.get(target) if success else None,
                    "length": math.dist(loc, end) if loc and end else None,
                    "angle": math.atan2(end[1] - loc[1], end[0] - loc[0])
                    if loc and end
                    else None,
                    "end_x": end[0] if end else None,
                    "end_y": end[1] if end else None,
                    "outcome": None
                    if success
                    else {
                        "id": 76 if row["pass_outcome"] == "offside" else 9,
                        "name": "Pass Offside"
                        if row["pass_outcome"] == "offside"
                        else "Incomplete",
                    },
                    "height": {"id": 3, "name": "High Pass"} if high is True else None,
                    "body_part": {"id": 37, "name": "Head"}
                    if row["is_header"] == "True"
                    else None,
                }
            )
        elif code == 16:
            tables["event_shots"].append(
                {
                    "event_id": eid,
                    "event_type_id": 16,
                    "match_id": mid,
                    "team_id": teams[side],
                    "statsbomb_xg": None,
                    "outcome": {
                        "id": 0,
                        "name": "Unknown (source shot outcome unavailable)",
                    },
                    "body_part": {"id": 37, "name": "Head"}
                    if row["is_header"] == "True"
                    else None,
                }
            )
    for period, pd in periods.items():
        for ms, code, name in (
            (0, 18, "Half Start"),
            (pd["duration_ms"], 34, "Half End"),
        ):
            tables["events"].append(
                {
                    "event_id": uid(f"boundary/{period}/{code}"),
                    "match_id": mid,
                    "period": period,
                    "timestamp": clock(ms),
                    "minute": (period - 1) * 45 + ms // 60000,
                    "second": ms // 1000 % 60,
                    "type_id": code,
                    "type_name": name,
                    "details": {},
                    "raw_payload": payload(derived_from="provider period metadata"),
                    "_ms": ms,
                }
            )
    tables["events"].sort(key=lambda e: (e["period"], e["_ms"]))
    for index, event in enumerate(tables["events"], 1):
        event["event_index"] = index
        ms = event.pop("_ms")
        nearest = min(
            periods[event["period"]]["duration_ms"] // STEP * STEP,
            round(ms / STEP) * STEP,
        )
        tables["event_tracking_links"].append(
            {
                "event_id": event["event_id"],
                "run_id": run,
                "match_id": mid,
                "period": event["period"],
                "frame_index": nearest // STEP,
                "alignment_method": "exact" if ms == nearest else "within_tolerance",
            }
        )
    tables["matches"].append(
        {
            "match_id": mid,
            "competition_id": 902,
            "season_id": 2025,
            "match_date": meta["date_time"],
            "home_score": meta["home_team_score"],
            "away_score": meta["away_team_score"],
            "match_status": "available",
            "match_status_360": "unavailable",
            "data_version": VERSION,
            "raw_payload": payload(
                masking="Player and team names/IDs replaced per match; public match provenance retained",
                shot_outcomes_available=False,
            ),
        }
    )
    tables["tracking_runs"].append(
        {
            "run_id": run,
            "match_id": mid,
            "label": f"SkillCorner real pseudonymized match {game}",
            "generator_name": "skillcorner-import",
            "generator_version": VERSION,
            "sample_rate_hz": 5,
            "pitch_length_m": 105,
            "pitch_width_m": 68,
            "is_synthetic": False,
            "max_event_offset_ms": 100,
            "config": payload(
                source_hz=10,
                stored_hz=5,
                source_pitch_length_m=length,
                source_pitch_width_m=width,
                coordinates="Affine to fixed 105x68 metres; x right, y down; source centre origin and y up",
                sample_selection="Every second original frame; detected and provider-extrapolated observations remain distinct",
                ball_in_play_method="Provider phases of play; missing phase means dead/unknown",
                xg_available=False,
                shot_outcomes_available=False,
                role_source="Provider player_role text; no formation imposed",
                missing_policy="No local trajectory reconstruction; source jumps over 13 m/s players or 55 m/s ball are marked missing",
            ),
        }
    )
    for p, pd in periods.items():
        tables["tracking_periods"].append(
            {
                "run_id": run,
                "match_id": mid,
                "period": p,
                "duration_ms": pd["duration_ms"],
                "home_attacks_positive_x": pd["home_positive"],
            }
        )
    phases = list(
        csv.DictReader(
            (CACHE / f"{source_id}_phases_of_play.csv").open(
                encoding="utf-8", newline=""
            )
        )
    )
    live_intervals = defaultdict(list)
    for phase in phases:
        p = int(phase["period"])
        if p in periods:
            live_intervals[p].append(
                (int(phase["frame_start"]), int(phase["frame_end"]))
            )
    for values in live_intervals.values():
        values.sort()
    folder = CACHE / f"prepared-{game}"
    folder.mkdir(exist_ok=True)
    counts = {}
    quality = Counter()
    samples = Counter()
    previous = {}

    def write(name, rows):
        count = 0
        with gzip.open(folder / f"{name}.jsonl.gz", "wt", encoding="utf-8") as output:
            for row in rows:
                output.write(
                    json.dumps(row, allow_nan=False, separators=(",", ":")) + "\n"
                )
                count += 1
        counts[name] = count

    for name, rows in tables.items():
        write(name, rows)

    def valid(key, point, ms, limit):
        if point is None:
            return None
        old = previous.get(key)
        previous[key] = (ms, point)
        if not (-5 <= point[0] <= 110 and -5 <= point[1] <= 73):
            quality["out_of_bounds"] += 1
            return None
        if (
            old
            and ms - old[0] == STEP
            and math.dist(point, old[1]) * 1000 / STEP > limit
        ):
            quality["source_jump"] += 1
            return None
        return point

    outputs = {
        name: gzip.open(folder / f"{name}.jsonl.gz", "wt", encoding="utf-8")  # noqa: SIM115 -- all handles close in the shared finally below
        for name in (
            "tracking_frames",
            "tracking_player_positions",
            "tracking_ball_positions",
        )
    }

    def emit(name, row):
        outputs[name].write(
            json.dumps(row, allow_nan=False, separators=(",", ":")) + "\n"
        )
        counts[name] = counts.get(name, 0) + 1

    try:
        with (CACHE / f"{source_id}_tracking_extrapolated.jsonl").open(
            encoding="utf-8"
        ) as source:
            for line in source:
                raw = json.loads(line)
                p = raw.get("period")
                if p not in periods:
                    continue
                pd = periods[p]
                frame = int(raw["frame"])
                ms = (frame - pd["start_frame"]) * 100
                if ms < 0 or ms > pd["duration_ms"] or ms % STEP:
                    continue
                key = {
                    "run_id": run,
                    "match_id": mid,
                    "period": p,
                    "frame_index": ms // STEP,
                }
                samples[p] += 1
                live = any(a <= frame <= b for a, b in live_intervals[p])
                emit(
                    "tracking_frames",
                    {**key, "period_time_ms": ms, "ball_in_play": live},
                )
                source_players = {r["player_id"]: r for r in raw["player_data"]}
                for (period, opid), span in spans.items():
                    if period != p or not (
                        span["a"] <= frame <= span["b"]
                        or frame == pd["end_frame"]
                        and span["b"] >= frame - 1
                    ):
                        continue
                    row = source_players.get(opid, {})
                    point = valid((p, opid), fixed(row.get("x"), row.get("y")), ms, 13)
                    method = (
                        "observed" if row.get("is_detected") is True else "extrapolated"
                    )
                    if point is None:
                        method = "missing"
                    quality["player_" + method] += 1
                    emit(
                        "tracking_player_positions",
                        {
                            **key,
                            "team_id": teams[span["side"]],
                            "player_id": pids[opid],
                            "x_m": point[0] if point else None,
                            "y_m": point[1] if point else None,
                            "is_on_pitch": True,
                            "on_pitch_slot": span["slot"],
                            "position_status": "available" if point else "missing",
                            "sample_method": method,
                            "confidence": None,
                        },
                    )
                ball = raw.get("ball_data") or {}
                point = valid((p, "ball"), fixed(ball.get("x"), ball.get("y")), ms, 55)
                method = (
                    "observed" if ball.get("is_detected") is True else "extrapolated"
                )
                if point is None:
                    method = "missing"
                quality["ball_" + method] += 1
                emit(
                    "tracking_ball_positions",
                    {
                        **key,
                        "x_m": point[0] if point else None,
                        "y_m": point[1] if point else None,
                        "z_m": max(0, ball["z"])
                        if point and ball.get("z") is not None
                        else None,
                        "position_status": "available" if point else "missing",
                        "sample_method": method,
                        "confidence": None,
                    },
                )
    finally:
        for output in outputs.values():
            output.close()
    for p, pd in periods.items():
        assert samples[p] == pd["duration_ms"] // STEP + 1, (
            source_id,
            p,
            samples[p],
            pd["duration_ms"],
        )
    report = {
        "match_id": mid,
        "source_match_id": source_id,
        "game": game,
        "run_id": run,
        "version": VERSION,
        "is_synthetic": False,
        "source_revision": manifest["revision"],
        "counts": counts,
        "quality": dict(quality),
        "score": [meta["home_team_score"], meta["away_team_score"]],
        "periods": periods,
        "five_minutes": {
            "duration_ms": 300000,
            "samples": 1500,
            "sample_step_ms": STEP,
        },
    }
    (folder / "manifest.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "match": mid,
                "source": source_id,
                "counts": counts,
                "quality": dict(quality),
            }
        ),
        flush=True,
    )
    return report


def main():
    source = json.loads(
        (ROOT / "database/azure-sql/skillcorner-source.json").read_text()
    )
    for entry in source["files"]:
        assert (
            hashlib.sha256((CACHE / entry["file"]).read_bytes()).hexdigest()
            == entry["sha256"]
        )
    reports = [prepare(i + 1, mid, source) for i, mid in enumerate(source["match_ids"])]
    (ROOT / "database/azure-sql/skillcorner-quality-report.json").write_text(
        json.dumps(
            {
                "provider": "SkillCorner",
                "data_kind": "real_pseudonymized",
                "reports": reports,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
