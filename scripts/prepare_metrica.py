"""Normalize real anonymized Metrica samples; never synthesize trajectories.

Keeps every fifth original 25 Hz observation (5 Hz), source event durations,
periods including added time, and explicit missing observations. Raw CSVs stay
in the ignored cache; reproducible attribution/checksums are versioned.
"""

import csv
import gzip
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache/metrica"
VERSION = "metrica-anonymized-1.0.0"
STEP_MS = 200


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def clock(ms):
    return (
        f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02}.{ms % 1000:03}"
    )


def lineup_clock(ms):
    return f"{ms // 60000:02}:{ms // 1000 % 60:02}.{ms % 1000:03}"


def identifier(game, value):
    return str(uuid5(NAMESPACE_URL, f"inside-game/metrica/{VERSION}/{game}/{value}"))


def source_payload(manifest, game, **extra):
    return {
        "is_synthetic": False,
        "data_kind": "real_anonymized",
        "provider": "Metrica Sports",
        "version": VERSION,
        "source_game": game,
        "source_revision": manifest["revision"],
        "source_url": manifest["repository"],
        **extra,
    }


def read_tracking(game):
    streams, readers, columns = [], [], []
    for side in ("Home", "Away"):
        stream = (CACHE / f"Sample_Game_{game}_RawTrackingData_{side}_Team.csv").open(
            newline=""
        )
        streams.append(stream)
        reader = csv.reader(stream)
        next(reader)
        next(reader)
        header = next(reader)
        columns.append(
            [
                (i, int(header[i].replace("Player", "").strip()))
                for i in range(3, len(header) - 2, 2)
            ]
        )
        readers.append(reader)
    frames, periods, spans = [], {}, {}
    try:
        for home, away in zip(*readers, strict=True):
            assert home[:3] == away[:3], "Tracking clocks differ between teams"
            period, source_frame = int(home[0]), int(home[1])
            source_ms = round(float(home[2]) * 1000)
            meta = periods.setdefault(
                period, {"first_frame": source_frame, "source_start_ms": source_ms}
            )
            meta["source_end_ms"] = source_ms
            if (source_frame - meta["first_frame"]) % 5:
                continue
            ms = source_ms - meta["source_start_ms"]
            players = {}
            for side, row in enumerate((home, away)):
                for i, jersey in columns[side]:
                    x, y = number(row[i]), number(row[i + 1])
                    if x is None or y is None:
                        continue
                    players[jersey] = (side, x * 105, y * 68)
                    span = spans.setdefault(
                        jersey,
                        {"side": side, "first": (period, ms), "last": (period, ms)},
                    )
                    span["last"] = period, ms
            ball = tuple(number(v) for v in home[-2:])
            away_ball = tuple(number(v) for v in away[-2:])
            assert ball == away_ball, "The source ball differs between team files"
            frames.append(
                {
                    "period": period,
                    "ms": ms,
                    "source_frame": source_frame,
                    "players": players,
                    "ball": None if None in ball else (ball[0] * 105, ball[1] * 68),
                }
            )
    finally:
        for stream in streams:
            stream.close()
    offset = 0
    for period, meta in sorted(periods.items()):
        meta["duration_ms"] = meta["source_end_ms"] - meta["source_start_ms"]
        meta["offset_ms"] = offset
        offset += meta["duration_ms"]
    # Role slots identify a goalkeeper and distinguish active players. They do
    # not claim an unprovided formation or tactical position.
    for side in (0, 1):
        ordered = sorted(
            (n for n, s in spans.items() if s["side"] == side),
            key=lambda n: (spans[n]["first"], n),
        )
        keeper = 11 if side == 0 else 25
        starters = [keeper] + [
            n for n in ordered if spans[n]["first"] == (1, 0) and n != keeper
        ]
        assert len(starters) == 11
        for slot, n in enumerate(starters, 1):
            spans[n]["slot"] = slot
        used = set()
        for incoming in ordered:
            if "slot" in spans[incoming]:
                continue
            first = spans[incoming]["first"]
            candidates = [
                n
                for n in ordered
                if "slot" in spans[n] and n not in used and spans[n]["last"] <= first
            ]
            assert candidates, (
                f"Cannot identify substitution slot from source presence: {incoming}, {first}, {spans}"
            )
            outgoing = max(candidates, key=lambda n: spans[n]["last"])
            used.add(outgoing)
            spans[incoming]["slot"] = spans[outgoing]["slot"]
            spans[incoming]["replaces"] = outgoing
            if spans[outgoing]["last"] == first:
                spans[outgoing]["last"] = first[0], first[1] - STEP_MS
                spans[outgoing]["handoff_overlap_ms"] = STEP_MS
    return frames, periods, spans


def prepare_game(game, manifest):
    frames, periods, spans = read_tracking(game)
    match_id, run_id = 900010 + game, identifier(game, "run")
    teams = [100 + game * 2, 101 + game * 2]
    player_id = lambda n: game * 1000 + n
    tables = defaultdict(list)
    payload = lambda **extra: source_payload(manifest, game, **extra)
    tables["teams"] = [
        {
            "team_id": teams[s],
            "team_name": f"Metrica {game} · Equipo {'A' if s == 0 else 'B'}",
        }
        for s in (0, 1)
    ]
    for n, span in spans.items():
        side = span["side"]
        tables["players"].append(
            {"player_id": player_id(n), "player_name": f"M{game} Jugador {n:02}"}
        )
        tables["match_lineups"].append(
            {
                "match_id": match_id,
                "team_id": teams[side],
                "player_id": player_id(n),
                "jersey_number": n,
                "raw_payload": payload(source_player=f"Player{n}"),
            }
        )
        p, ms = span["first"]
        end_p, end_ms = span["last"]
        start = periods[p]["offset_ms"] + ms
        end = periods[end_p]["offset_ms"] + min(
            end_ms + STEP_MS, periods[end_p]["duration_ms"]
        )
        tables["lineup_positions"].append(
            {
                "match_id": match_id,
                "team_id": teams[side],
                "player_id": player_id(n),
                "position_index": 0,
                "position_id": 1 if span["slot"] == 1 else None,
                "position": "Goalkeeper" if span["slot"] == 1 else None,
                "from_time": lineup_clock(start),
                "to_time": lineup_clock(end),
                "from_period": p,
                "to_period": end_p,
                "start_reason": "Starting XI"
                if start == 0
                else "Tracking presence (inferred substitution)",
                "end_reason": "Tracking interval end",
            }
        )
    for side in (0, 1):
        tables["match_teams"].append(
            {
                "match_id": match_id,
                "team_id": teams[side],
                "side": "home" if side == 0 else "away",
                "lineup_raw_payload": payload(formation=None),
            }
        )
    source_events = list(
        csv.DictReader(
            (CACHE / f"Sample_Game_{game}_RawEventsData.csv").open(newline="")
        )
    )
    dead_windows, goals, possession, previous_side, restarts = [], [0, 0], 0, None, {}
    restart_codes = {
        "KICK OFF": (65, "Kick Off"),
        "THROW IN": (67, "Throw-in"),
        "CORNER KICK": (61, "Corner"),
        "FREE KICK": (62, "Free Kick"),
    }
    event_types = {
        "PASS": (30, "Pass"),
        "SHOT": (16, "Shot"),
        "RECOVERY": (2, "Ball Recovery"),
        "BALL LOST": (1001, "Metrica Ball Lost"),
        "CHALLENGE": (1002, "Metrica Challenge"),
        "BALL OUT": (1003, "Ball Out"),
        "SET PIECE": (1004, "Set Piece"),
        "FAULT RECEIVED": (21, "Foul Won"),
        "CARD": (24, "Bad Behaviour"),
    }
    for index, row in enumerate(source_events):
        period, side = int(row["Period"]), 0 if row["Team"] == "Home" else 1
        ms = (
            round(float(row["Start Time [s]"]) * 1000)
            - periods[period]["source_start_ms"]
        )
        ms = max(0, ms)
        end_ms = (
            round(float(row["End Time [s]"]) * 1000)
            - periods[period]["source_start_ms"]
        )
        duration = max(0, end_ms - ms) / 1000
        subtype, kind = row["Subtype"], row["Type"]
        n = (
            int(row["From"].replace("Player", "").strip())
            if row["From"].strip()
            else None
        )
        target = (
            int(row["To"].replace("Player", "").strip()) if row["To"].strip() else None
        )
        code, name = event_types[kind]
        details = {
            "metrica": {"type": kind, "subtype": subtype, "source_row": index + 1}
        }
        if kind == "RECOVERY" and "INTERCEPTION" in subtype:
            code, name = 10, "Interception"
            details["interception"] = {"outcome": {"id": 16, "name": "Success In Play"}}
        elif kind == "RECOVERY" and subtype == "SAVED":
            code, name = 23, "Goal Keeper"
            details["goalkeeper"] = {"type": {"id": 33, "name": "Shot Saved"}}
        elif kind == "CHALLENGE" and subtype in ("TACKLE-WON", "TACKLE-LOST"):
            code, name = 4, "Duel"
            details["duel"] = {
                "type": {"id": 11, "name": "Tackle"},
                "outcome": {
                    "id": 4 if subtype.endswith("WON") else 13,
                    "name": "Won" if subtype.endswith("WON") else "Lost In Play",
                },
            }
        if kind == "SET PIECE":
            restarts[(period, side)] = (
                ms,
                next(
                    (v for key, v in restart_codes.items() if subtype.startswith(key)),
                    None,
                ),
            )
        if (
            kind == "BALL OUT"
            or (kind == "SHOT" and ("OUT" in subtype or "GOAL" in subtype))
            or kind == "FAULT RECEIVED"
        ):
            next_play = next(
                (
                    r
                    for r in source_events[index + 1 :]
                    if int(r["Period"]) == period and r["Type"] in ("PASS", "SHOT")
                ),
                None,
            )
            if next_play:
                resume = (
                    round(float(next_play["Start Time [s]"]) * 1000)
                    - periods[period]["source_start_ms"]
                )
                dead_windows.append((period, max(ms, end_ms), resume))
        if kind in ("PASS", "BALL LOST", "SHOT", "RECOVERY") and side != previous_side:
            possession += 1
            previous_side = side
        x, y, ex, ey = [
            number(row[k]) for k in ("Start X", "Start Y", "End X", "End Y")
        ]
        # Metrica uses a fixed pitch. Events in our canonical event tables are
        # oriented towards the acting team's attacking goal.
        home_positive = periods[period].get("home_positive")
        if home_positive is None:
            first = next(f for f in frames if f["period"] == period)
            periods[period]["home_positive"] = first["players"][11][1] < 52.5
        positive = periods[period]["home_positive"] == (side == 0)
        orient = lambda a, scale, positive=positive: (
            None if a is None else (a if positive else 1 - a) * scale
        )
        eid = identifier(game, f"event/{index}")
        e = {
            "event_id": eid,
            "match_id": match_id,
            "period": period,
            "timestamp": clock(ms),
            "minute": (period - 1) * 45 + ms // 60000,
            "second": ms // 1000 % 60,
            "type_id": code,
            "type_name": name,
            "team_id": teams[side],
            "player_id": player_id(n) if n else None,
            "possession": possession or None,
            "possession_team_id": teams[previous_side]
            if previous_side is not None
            else None,
            "location_x": orient(x, 120),
            "location_y": orient(y, 80),
            "duration": duration,
            "details": details,
            "raw_payload": payload(source_event=row),
            "_ms": ms,
        }
        tables["events"].append(e)
        if kind == "PASS":
            restart = restarts.pop((period, side), None)
            restart = restart[1] if restart and 0 <= ms - restart[0] <= 5000 else None
            tables["event_passes"].append(
                {
                    "event_id": eid,
                    "event_type_id": 30,
                    "match_id": match_id,
                    "team_id": teams[side],
                    "recipient_player_id": player_id(target) if target else None,
                    "end_x": orient(ex, 120),
                    "end_y": orient(ey, 80),
                    "length": math.hypot((ex - x) * 120, (ey - y) * 80)
                    if None not in (x, y, ex, ey)
                    else None,
                    "angle": math.atan2(
                        (ey - y) * (1 if positive else -1) * 80,
                        (ex - x) * (1 if positive else -1) * 120,
                    )
                    if None not in (x, y, ex, ey)
                    else None,
                    "outcome": None,
                    "pass_type": {"id": restart[0], "name": restart[1]}
                    if restart
                    else None,
                    "body_part": {"id": 37, "name": "Head"}
                    if "HEAD" in subtype
                    else None,
                    "height": None,
                    "shot_assist": None,
                    "goal_assist": None,
                }
            )
        elif kind == "SHOT":
            outcome = (
                (97, "Goal")
                if "GOAL" in subtype
                else (100, "Saved")
                if "SAVED" in subtype
                else (96, "Blocked")
                if "BLOCKED" in subtype
                else (99, "Post")
                if "WOODWORK" in subtype
                else (98, "Off T")
            )
            if outcome[0] == 97:
                goals[side] += 1
            tables["event_shots"].append(
                {
                    "event_id": eid,
                    "event_type_id": 16,
                    "match_id": match_id,
                    "team_id": teams[side],
                    "statsbomb_xg": None,
                    "end_x": orient(ex, 120),
                    "end_y": orient(ey, 80),
                    "end_z": None,
                    "outcome": {"id": outcome[0], "name": outcome[1]},
                    "body_part": {"id": 37, "name": "Head"}
                    if "HEAD" in subtype
                    else None,
                }
            )
        elif kind == "CARD" and n:
            tables["lineup_cards"].append(
                {
                    "match_id": match_id,
                    "team_id": teams[side],
                    "player_id": player_id(n),
                    "card_index": sum(
                        r["player_id"] == player_id(n) for r in tables["lineup_cards"]
                    ),
                    "time": lineup_clock((period - 1) * 2700000 + ms),
                    "period": period,
                    "card_type": "Yellow Card",
                    "reason": "Metrica source card",
                }
            )
    # Boundaries and substitution identity changes are derived, clearly labelled.
    for period, meta in periods.items():
        for ms, code, name in (
            (0, 18, "Half Start"),
            (meta["duration_ms"], 34, "Half End"),
        ):
            tables["events"].append(
                {
                    "event_id": identifier(game, f"boundary/{period}/{code}"),
                    "match_id": match_id,
                    "period": period,
                    "timestamp": clock(ms),
                    "minute": (period - 1) * 45 + ms // 60000,
                    "second": ms // 1000 % 60,
                    "type_id": code,
                    "type_name": name,
                    "details": {},
                    "raw_payload": payload(derived_from="source period boundaries"),
                    "_ms": ms,
                }
            )
    for n, span in spans.items():
        if "replaces" not in span:
            continue
        p, ms = span["first"]
        tables["events"].append(
            {
                "event_id": identifier(game, f"substitution/{n}"),
                "match_id": match_id,
                "period": p,
                "timestamp": clock(ms),
                "minute": (p - 1) * 45 + ms // 60000,
                "second": ms // 1000 % 60,
                "type_id": 19,
                "type_name": "Substitution",
                "team_id": teams[span["side"]],
                "player_id": player_id(span["replaces"]),
                "details": {
                    "substitution": {
                        "replacement": {
                            "id": player_id(n),
                            "name": f"M{game} Jugador {n:02}",
                        }
                    }
                },
                "raw_payload": payload(
                    derived_from="first/last tracking presence; not a separately annotated source event"
                ),
                "_ms": ms,
            }
        )
    tables["events"].sort(key=lambda e: (e["period"], e["_ms"]))
    last_frame = {p: max(f["ms"] for f in frames if f["period"] == p) for p in periods}
    for i, e in enumerate(tables["events"], 1):
        e["event_index"] = i
        ms = e.pop("_ms")
        nearest = min(last_frame[e["period"]], round(ms / STEP_MS) * STEP_MS)
        tables["event_tracking_links"].append(
            {
                "event_id": e["event_id"],
                "run_id": run_id,
                "match_id": match_id,
                "period": e["period"],
                "frame_index": nearest // STEP_MS,
                "alignment_method": "exact" if nearest == ms else "within_tolerance",
            }
        )
    tables["matches"].append(
        {
            "match_id": match_id,
            "competition_id": 901,
            "season_id": 1900,
            "match_date": "1900-01-01T00:00:00Z",
            "home_score": goals[0],
            "away_score": goals[1],
            "match_status": "available",
            "match_status_360": "unavailable",
            "data_version": VERSION,
            "raw_payload": payload(
                date_unknown=True, date_placeholder="1900-01-01", formation_unknown=True
            ),
        }
    )
    tables["tracking_runs"].append(
        {
            "run_id": run_id,
            "match_id": match_id,
            "label": f"Metrica real anonymized game {game}",
            "generator_name": "metrica-sports-import",
            "generator_version": VERSION,
            "sample_rate_hz": 5,
            "pitch_length_m": 105,
            "pitch_width_m": 68,
            "is_synthetic": False,
            "max_event_offset_ms": 160,
            "config": payload(
                source_hz=25,
                stored_hz=5,
                sample_selection="every fifth original observation; no coordinate interpolation",
                source_time_offset_ms={
                    p: m["source_start_ms"] for p, m in periods.items()
                },
                ball_height_available=False,
                xg_available=False,
                formation_available=False,
                ball_in_play_method="inferred from source ball-out/shot/foul events until next pass/shot; not provider truth",
                missing_policy="retain missing samples; mask implausible source jumps, never invent trajectories",
            ),
        }
    )
    for p, meta in periods.items():
        tables["tracking_periods"].append(
            {
                "run_id": run_id,
                "match_id": match_id,
                "period": p,
                "duration_ms": meta["duration_ms"],
                "home_attacks_positive_x": meta["home_positive"],
            }
        )
    target = CACHE / f"prepared-{game}"
    target.mkdir(exist_ok=True)
    counts, excluded, max_speeds, previous = (
        {},
        Counter(),
        {"players_m_s": 0, "ball_m_s": 0},
        {},
    )

    def write(name, rows):
        with gzip.open(target / f"{name}.jsonl.gz", "wt", encoding="utf-8") as output:
            count = 0
            for row in rows:
                output.write(
                    json.dumps(row, allow_nan=False, separators=(",", ":")) + "\n"
                )
                count += 1
        counts[name] = count

    for name, rows in tables.items():
        write(name, rows)

    def valid_position(key, point, frame, limit, label):
        if point is None:
            return None
        old = previous.get(key)
        previous[key] = frame["ms"], point
        if not (-5 <= point[0] <= 110 and -5 <= point[1] <= 73):
            excluded[label + "_out_of_bounds"] += 1
            return None
        if old and frame["ms"] - old[0] == STEP_MS:
            speed = math.dist(point, old[1]) * 1000 / STEP_MS
            if speed > limit:
                excluded[label + "_source_jump"] += 1
                return None
            max_speeds[label + "_m_s"] = max(max_speeds[label + "_m_s"], speed)
        return point

    def frame_rows():
        for frame in frames:
            p, ms = frame["period"], frame["ms"]
            yield {
                "run_id": run_id,
                "match_id": match_id,
                "period": p,
                "frame_index": ms // STEP_MS,
                "period_time_ms": ms,
                "ball_in_play": frame["ball"] is not None
                and not any(dp == p and a <= ms < b for dp, a, b in dead_windows),
            }

    def player_rows():
        for frame in frames:
            p, ms = frame["period"], frame["ms"]
            for n, span in spans.items():
                if not span["first"] <= (p, ms) <= span["last"]:
                    continue
                found = frame["players"].get(n)
                point = valid_position(
                    (p, n), found[1:] if found else None, frame, 13, "players"
                )
                if point is None:
                    excluded["missing_player_samples"] += 1
                yield {
                    "run_id": run_id,
                    "match_id": match_id,
                    "period": p,
                    "frame_index": ms // STEP_MS,
                    "team_id": teams[span["side"]],
                    "player_id": player_id(n),
                    "x_m": point[0] if point else None,
                    "y_m": point[1] if point else None,
                    "is_on_pitch": True,
                    "on_pitch_slot": span["slot"],
                    "position_status": "available" if point else "missing",
                    "sample_method": "observed" if point else "missing",
                    "confidence": None,
                }

    def ball_rows():
        for frame in frames:
            point = valid_position(
                (frame["period"], "ball"), frame["ball"], frame, 55, "ball"
            )
            if point is None:
                excluded["missing_ball_samples"] += 1
            yield {
                "run_id": run_id,
                "match_id": match_id,
                "period": frame["period"],
                "frame_index": frame["ms"] // STEP_MS,
                "x_m": point[0] if point else None,
                "y_m": point[1] if point else None,
                "z_m": None,
                "position_status": "available" if point else "missing",
                "sample_method": "observed" if point else "missing",
                "confidence": None,
            }

    write("tracking_frames", frame_rows())
    write("tracking_player_positions", player_rows())
    write("tracking_ball_positions", ball_rows())
    report = {
        "match_id": match_id,
        "game": game,
        "run_id": run_id,
        "version": VERSION,
        "is_synthetic": False,
        "source_revision": manifest["revision"],
        "counts": counts,
        "source_event_types": dict(Counter(r["Type"] for r in source_events)),
        "periods": periods,
        "score": goals,
        "excluded_source_samples": dict(excluded),
        "max_retained_adjacent_speed": max_speeds,
        "five_minutes": {
            "duration_ms": 300000,
            "sample_step_ms": STEP_MS,
            "samples": sum(f["period"] == 1 and f["ms"] < 300000 for f in frames),
        },
    }
    assert report["five_minutes"]["samples"] == 1500
    (target / "manifest.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main():
    manifest = json.loads((ROOT / "database/azure-sql/metrica-source.json").read_text())
    for entry in manifest["files"]:
        assert (
            hashlib.sha256((CACHE / entry["file"]).read_bytes()).hexdigest()
            == entry["sha256"]
        ), "Source checksum mismatch"
    reports = [prepare_game(game, manifest) for game in (1, 2)]
    (ROOT / "database/azure-sql/metrica-quality-report.json").write_text(
        json.dumps(
            {
                "source": manifest["repository"],
                "data_kind": "real_anonymized",
                "reports": reports,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    for report in reports:
        print(json.dumps(report))


if __name__ == "__main__":
    main()
