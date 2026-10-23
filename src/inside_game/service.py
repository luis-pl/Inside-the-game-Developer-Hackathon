"""Closed operation registry and deterministic orchestration, independent of HTTP."""

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections import Counter, defaultdict
from math import hypot
from uuid import uuid4

from inside_game import contracts as c
from inside_game.analytics import (
    EVENT_TYPES,
    PROFILES,
    RESTARTS,
    ZONES,
    aerial_contests,
    code,
    defensive_kind,
    events_for,
    possession_rows,
    ratio,
    sequence_rows,
    summary,
    won_lost,
)
from inside_game.errors import DomainError
from inside_game.tools import topology

DATA_OPERATIONS = {
    "describe_dataset": c.Empty,
    "find_entities": c.EntitySearch,
    "list_matches": c.MatchList,
    "get_match_context": c.MatchRequest,
    "get_team_summary": c.TeamSummary,
    "get_player_summary": c.PlayerSummary,
    "get_shots": c.ShotsRequest,
    "get_passes": c.PassesRequest,
    "get_defensive_actions": c.DefensiveRequest,
    "get_ball_actions": c.BallRequest,
    "get_discipline": c.Filtered,
    "get_substitutions": c.Filtered,
    "get_possessions": c.Filtered,
    "get_tracking_frame": c.TrackingFrame,
    "get_tracking_window": c.TrackingWindow,
    "get_event_context": c.EventContext,
    "get_heatmap": c.HeatmapRequest,
    "get_movement_summary": c.MovementRequest,
    "get_metric_series": c.MetricSeries,
    "compare_entities": c.CompareRequest,
    "get_set_piece_sequences": c.SetPiecesRequest,
    "get_events": c.EventsRequest,
    "get_sequences": c.SequenceRequest,
    "get_zone_summary": c.ZoneRequest,
    "get_rankings": c.RankingsRequest,
}
SPATIAL_OPERATIONS = {
    name: c.SpatialRequest
    for name in (
        "get_team_shape",
        "get_proximity_connectivity",
        "get_space_coverage",
        "get_passing_network",
        "get_pass_corridor",
        "get_line_breaks",
        "get_persistent_structure",
        "get_node_removal_robustness",
        "get_defensive_profile",
    )
}
OPERATIONS = {**DATA_OPERATIONS, **SPATIAL_OPERATIONS}
RANK_PROFILES = {
    "shots": "finishing",
    "goals": "finishing",
    "xg": "finishing",
    "assists": "chance_creation",
    "completed_passes": "passing",
    "tackles_won": "defending",
    "interceptions": "defending",
    "dribbles_complete": "ball_progression",
    "distance_m": "movement",
    "saves": "goalkeeping",
}


class AnalyticsService:
    def __init__(self, repository):
        self.repo = repository
        self.cursor_key = secrets.token_bytes(32)

    def execute(self, operation, request, request_id=None):
        if operation not in OPERATIONS:
            raise DomainError(
                "UNREGISTERED_OPERATION", "Operation is not registered.", 404
            )
        datasets = []
        if hasattr(request, "match_id") and request.match_id is not None:
            data = self.repo.match(request.match_id)
            self.validate(data, request)
            datasets = [data]
        elif hasattr(request, "match_ids"):
            if len(set(request.match_ids)) != len(request.match_ids):
                raise DomainError("INVALID_ARGUMENT", "match_ids must be unique.")
            datasets = [self.repo.match(mid) for mid in request.match_ids]
            for data in datasets:
                self.validate(
                    data,
                    request,
                    entities=operation != "get_rankings"
                    and operation != "compare_entities",
                )
        elif operation == "get_event_context":
            data = self.repo.event_match(str(request.event_id))
            datasets = [data]
        else:
            data = None
        if operation in SPATIAL_OPERATIONS:
            result = self.spatial(operation, request, datasets[0])
        else:
            result = self.dispatch(operation, request, datasets)
        warnings = [
            "Synthetic football data; xG is toy-distance-angle-v2, not a calibrated provider model."
        ]
        if any(d["meta"]["generator_version"] != "3.0.0" for d in datasets):
            warnings.append(
                "Dataset generation differs from the audited 3.0.0 scenario."
            )
        if (
            getattr(request, "zone_id", "all") != "all"
            or getattr(request, "score_state", "all") != "all"
            or getattr(request, "pressure", "all") != "all"
        ):
            warnings.append(
                "Event filters condition action counts. Playing minutes remain the covered time in the requested scope."
            )
        if operation == "get_possessions":
            warnings.append("Recorded event span is not exact temporal possession.")
        if operation == "get_space_coverage":
            warnings.append(
                "Voronoi area is geometric proximity, not pitch-control probability."
            )
        return c.ApiResponse(
            operation_id=operation,
            method_id=operation + "_v1",
            request_id=request_id or str(uuid4()),
            scope=request.model_dump(mode="json", exclude={"cursor"}),
            data=result,
            provenance={
                "is_synthetic": all(d["meta"]["is_synthetic"] for d in datasets)
                if datasets
                else True,
                "datasets": [
                    {
                        "match_id": d["meta"]["match_id"],
                        "generator_version": d["meta"]["generator_version"],
                        "dataset_revision": d["revision"],
                        "run_ids": [r["run_id"] for r in d["tracking_runs"]],
                    }
                    for d in datasets
                ],
            },
            coordinates={
                "events": "acting_team_120x80",
                "tracking": "fixed_pitch_metres",
                "spatial": "fixed_pitch_metres unless attacking_axis explicitly stated",
                "pitch_length_m": 105,
                "pitch_width_m": 68,
            },
            coverage={
                "match_count": len(datasets),
                "source": "published Azure SQL analytics views",
                **result.pop("_coverage", {}),
            },
            pagination=result.pop("_pagination", {}),
            warnings=warnings + result.pop("_warnings", []),
        )

    def validate(self, data, req, entities=True):
        teams = {t["team_id"] for t in data["match_teams"]}
        players = {p["player_id"]: p["team_id"] for p in data["match_lineups"]}
        team, player = getattr(req, "team_id", None), getattr(req, "player_id", None)
        if entities and (
            (team is not None and team not in teams)
            or (player is not None and player not in players)
            or (team is not None and player is not None and players[player] != team)
        ):
            raise DomainError(
                "ENTITY_NOT_IN_MATCH",
                "Selected team/player does not belong to the match.",
            )
        scope = getattr(req, "scope", c.MatchScope())
        durations = {
            p["period"]: int(p["duration_ms"]) for p in data["tracking_periods"]
        }
        if scope.kind != "match" and (
            scope.period not in durations
            or scope.kind == "window"
            and scope.end_ms > durations[scope.period]
        ):
            raise DomainError(
                "INVALID_ARGUMENT", "Scope extends beyond the available period."
            )

    def run(self, data, requested=None):
        runs = [
            r
            for r in data["tracking_runs"]
            if requested is None or r["run_id"] == str(requested)
        ]
        if len(runs) != 1:
            raise DomainError(
                "RUN_AMBIGUOUS" if requested is None else "RUN_NOT_FOUND",
                "Select one available tracking run.",
            )
        return runs[0]

    def bounds(self, data, scope):
        if scope.kind == "match":
            return None, 0, max(int(p["duration_ms"]) for p in data["tracking_periods"])
        duration = next(
            int(p["duration_ms"])
            for p in data["tracking_periods"]
            if p["period"] == scope.period
        )
        return (
            scope.period,
            getattr(scope, "start_ms", 0),
            getattr(scope, "end_ms", duration),
        )

    def covered_minutes(self, data, scope, player=None):
        periods = {
            p["period"]: int(p["duration_ms"]) / 1000 for p in data["tracking_periods"]
        }
        period, start, end = self.bounds(data, scope)
        if player is None:
            return sum(
                (min(end, duration * 1000) - start) / 60000
                for p, duration in periods.items()
                if period is None or p == period
            )
        parse = lambda value: sum(
            int(n) * factor for n, factor in zip(value.split(":"), (60, 1))
        )
        total, offset = 0, 0
        intervals = [l for l in data["lineup_positions"] if l["player_id"] == player]
        for p, duration in sorted(periods.items()):
            if period is None or p == period:
                for interval in intervals:
                    total += max(
                        0,
                        min(
                            offset + end / 1000,
                            offset + duration,
                            parse(interval["to_time"]),
                        )
                        - max(
                            offset + start / 1000, offset, parse(interval["from_time"])
                        ),
                    )
            offset += duration
        return total / 60

    def page(self, operation, req, rows, revision="catalog"):
        args = req.model_dump(mode="json", exclude={"cursor"})
        signature = hashlib.sha256(
            json.dumps([operation, args, revision], sort_keys=True).encode()
        ).hexdigest()
        offset = 0
        if req.cursor:
            try:
                payload, mac = req.cursor.split(".")
                if not hmac.compare_digest(
                    hmac.new(
                        self.cursor_key, payload.encode(), hashlib.sha256
                    ).hexdigest(),
                    mac,
                ):
                    raise ValueError()
                cursor = json.loads(
                    base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
                )
                if cursor["signature"] != signature or cursor["expires"] < time.time():
                    raise ValueError()
                offset = cursor["offset"]
                if type(offset) is not int or not 0 <= offset <= len(rows):
                    raise ValueError()
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                raise DomainError(
                    "INVALID_CURSOR",
                    "Cursor is invalid, expired or belongs to another query.",
                ) from exc
        following = offset + req.limit
        cursor = None
        if following < len(rows):
            payload = (
                base64.urlsafe_b64encode(
                    json.dumps(
                        {
                            "offset": following,
                            "signature": signature,
                            "expires": int(time.time() + 1200),
                        }
                    ).encode()
                )
                .decode()
                .rstrip("=")
            )
            cursor = (
                payload
                + "."
                + hmac.new(
                    self.cursor_key, payload.encode(), hashlib.sha256
                ).hexdigest()
            )
        return {
            "total": len(rows),
            "items": rows[offset:following],
            "_pagination": {"next_cursor": cursor, "limit": req.limit},
        }

    def action_view(self, op, req, rows, data, profile):
        totals = summary(data, rows, profile)
        if req.view == "summary":
            return {"total": len(rows), "summary": totals}
        if req.view == "timeline":
            groups = defaultdict(list)
            for e in rows:
                groups[(e["period"], e["period_time_ms"] // (req.bin_s * 1000))].append(
                    e
                )
            return {
                "total": len(rows),
                "summary": totals,
                "series": [
                    {
                        "period": p,
                        "start_ms": b * req.bin_s * 1000,
                        "metrics": summary(data, es, profile),
                    }
                    for (p, b), es in sorted(groups.items())
                ],
            }
        return {**self.page(op, req, rows, data["revision"]), "summary": totals}

    def dispatch(self, op, req, datasets):
        data = datasets[0] if datasets else None
        if op == "describe_dataset":
            cat = self.repo.catalog()
            return {
                "matches": len(cat["matches"]),
                "data_operations": list(DATA_OPERATIONS),
                "spatial_operations": list(SPATIAL_OPERATIONS),
                "profiles": PROFILES,
                "zones_attacking_metres": ZONES,
                "sampling_hz": 1,
                "unobserved_scenarios": [
                    "penalty",
                    "red_card",
                    "offside",
                    "injury",
                    "extra_time",
                ],
                "unavailable_models": [
                    "xT",
                    "OBV",
                    "EPV",
                    "post_shot_xg",
                    "pitch_control",
                    "impenetrability_score",
                ],
            }
        if op == "list_matches":
            rows = []
            for m in self.repo.catalog()["matches"]:
                team_ids = [m["home_team_id"], m["away_team_id"]]
                if (
                    req.team_id is not None
                    and req.team_id not in team_ids
                    or req.opponent_id is not None
                    and req.opponent_id not in team_ids
                ):
                    continue
                if req.team_id is not None and req.opponent_id == req.team_id:
                    continue
                if req.side != "all" and (
                    req.team_id is None or m[req.side + "_team_id"] != req.team_id
                ):
                    continue
                if (
                    req.from_date
                    and m["match_date"][:10] < req.from_date.isoformat()
                    or req.to_date
                    and m["match_date"][:10] > req.to_date.isoformat()
                ):
                    continue
                rows.append(m)
            return self.page(
                op,
                req,
                rows,
                hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
            )
        if op == "find_entities":
            cat = self.repo.catalog()
            rows = cat["teams" if req.kind == "team" else "players"]
            name_key, id_key = (
                ("team_name", "team_id")
                if req.kind == "team"
                else ("player_name", "player_id")
            )
            rows = [r for r in rows if req.name.casefold() in r[name_key].casefold()]
            if data:
                valid = {
                    r[id_key]
                    for r in data[
                        "match_teams" if req.kind == "team" else "match_lineups"
                    ]
                }
                rows = [r for r in rows if r[id_key] in valid]
            return self.page(op, req, rows)
        if op == "get_match_context":
            return {
                "match": data["meta"],
                "lineups": data["match_lineups"],
                "position_intervals": data["lineup_positions"],
                "cards": data["lineup_cards"],
                "tactics": data["event_tactics"],
                "runs": data["tracking_runs"],
                "periods": data["tracking_periods"],
            }
        if op in (
            "get_team_summary",
            "get_player_summary",
            "compare_entities",
            "get_rankings",
        ):
            return self.reports(op, req, datasets)
        if op in ("get_tracking_frame", "get_tracking_window", "get_event_context"):
            return self.tracking(op, req, data)
        if op in ("get_movement_summary", "get_heatmap", "get_zone_summary"):
            return self.aggregates(op, req, data)
        rows = events_for(data, req)
        if op == "get_shots":
            outcomes = {
                "on_target": (97, 100, 116),
                "goal": (97,),
                "saved": (100, 115, 116),
                "blocked": (96,),
                "off_target": (98, 101, 115),
            }
            body = {"head": 37, "left_foot": 38, "right_foot": 40}
            rows = [
                e
                for e in rows
                if e["shot"]
                and (
                    req.outcome == "all"
                    or code(e["shot"]["outcome"]) in outcomes[req.outcome]
                )
                and (
                    req.body_part == "all"
                    or code(e["shot"]["body_part"]) == body[req.body_part]
                )
            ]
            return self.action_view(op, req, rows, data, "finishing")
        if op == "get_passes":
            heights = {"ground": 1, "low": 2, "high": 3}
            rows = [
                e
                for e in rows
                if e["pass"]
                and (
                    req.outcome == "all"
                    or (e["pass"]["outcome"] is None) == (req.outcome == "complete")
                )
                and (
                    req.height == "all"
                    or code(e["pass"]["height"]) == heights[req.height]
                )
                and (
                    req.restart == "all"
                    or code(e["pass"]["pass_type"]) == RESTARTS.get(req.restart)
                )
                and (req.tagged == "all" or e["pass"][req.tagged] is True)
            ]
            return self.action_view(op, req, rows, data, "passing")
        if op == "get_defensive_actions":
            if req.outcome != "all" and req.kind not in (
                "tackle",
                "aerial_duel",
                "fifty_fifty",
            ):
                raise DomainError(
                    "INVALID_ARGUMENT",
                    "won/lost applies to tackles, aerial duels or fifty_fifty.",
                )
            if req.kind == "aerial_duel":
                rows = aerial_contests(data, rows)
                rows = [
                    e
                    for e in rows
                    if req.outcome == "all" or e["outcome"] in ("both", req.outcome)
                ]
            else:
                rows = [
                    e
                    for e in rows
                    if defensive_kind(e) is not None
                    and (req.kind == "all" or defensive_kind(e) == req.kind)
                    and (req.outcome == "all" or won_lost(e) == req.outcome)
                ]
                if (
                    req.kind == "fifty_fifty"
                    and req.outcome == "all"
                    and req.team_id is None
                    and req.player_id is None
                ):
                    rows = [e for e in rows if won_lost(e) == "won"]
            return self.action_view(
                op,
                req,
                rows,
                data,
                "goalkeeping" if req.kind == "goalkeeper" else "defending",
            )
        if op == "get_ball_actions":
            types = {
                "dribble": 14,
                "carry": 43,
                "receipt": 42,
                "miscontrol": 38,
                "dispossessed": 3,
            }
            if req.outcome != "all" and req.kind != "dribble":
                raise DomainError(
                    "INVALID_ARGUMENT", "complete/incomplete applies to dribbles."
                )
            rows = [
                e
                for e in rows
                if e["type_id"] in types.values()
                and (req.kind == "all" or e["type_id"] == types[req.kind])
                and (
                    req.outcome == "all"
                    or code(e["details"].get("dribble", {}).get("outcome"))
                    == (8 if req.outcome == "complete" else 9)
                )
            ]
            return self.action_view(op, req, rows, data, "ball_progression")
        if op == "get_events":
            rows = [
                e
                for e in rows
                if not req.event_types or e["type_id"] in req.event_types
            ]
            return {
                **self.page(op, req, rows, data["revision"]),
                "counts_by_type": dict(Counter(e["type_name"] for e in rows)),
            }
        if op == "get_discipline":
            rows = [e for e in rows if e["type_id"] in (21, 22, 24)]
            return {
                **self.page(op, req, rows, data["revision"]),
                "fouls_committed": sum(e["type_id"] == 22 for e in rows),
                "fouls_won": sum(e["type_id"] == 21 for e in rows),
                "cards": [
                    e
                    for e in rows
                    if e["details"].get("foul_committed", {}).get("card")
                ],
            }
        if op == "get_substitutions":
            rows = [e for e in rows if e["type_id"] == 19]
            for e in rows:
                e["replacement"] = e["details"]["substitution"]["replacement"]
            return self.page(op, req, rows, data["revision"])
        if op == "get_possessions":
            return self.page(op, req, possession_rows(rows), data["revision"])
        if op == "get_sequences":
            return self.page(
                op,
                req,
                sequence_rows(data, rows, req.pattern_id, req.scope),
                data["revision"],
            )
        if op == "get_set_piece_sequences":
            sequences = []
            for e in rows:
                if (
                    not e["pass"]
                    or code(e["pass"]["pass_type"]) not in RESTARTS.values()
                    or req.restart != "all"
                    and code(e["pass"]["pass_type"]) != RESTARTS[req.restart]
                ):
                    continue
                chain = []
                for candidate in data["events"]:
                    if candidate["event_index"] < e["event_index"]:
                        continue
                    if (
                        candidate["period"] != e["period"]
                        or candidate["possession"] != e["possession"]
                        or candidate["event_index"] > e["event_index"]
                        and code(
                            data["passes"]
                            .get(candidate["event_id"], {})
                            .get("pass_type")
                        )
                        in RESTARTS.values()
                    ):
                        break
                    chain.append(candidate["event_id"])
                shots = [data["shots"][id] for id in chain if id in data["shots"]]
                sequences.append(
                    {
                        "restart_event_id": e["event_id"],
                        "restart": e["pass"]["pass_type"],
                        "period": e["period"],
                        "start_ms": e["period_time_ms"],
                        "event_ids": chain,
                        "shots": len(shots),
                        "xg": sum(s["statsbomb_xg"] or 0 for s in shots),
                    }
                )
            return self.page(op, req, sequences, data["revision"])
        if op == "get_metric_series":
            groups = defaultdict(list)
            for e in rows:
                groups[(e["period"], e["period_time_ms"] // (req.bin_s * 1000))].append(
                    e
                )
            if req.profile_id in ("movement", "ppda_demo"):
                raise DomainError(
                    "UNSUPPORTED_METRIC",
                    "Use movement summary or team ppda_demo summary for this profile.",
                )
            return {
                "series": [
                    {
                        "period": p,
                        "start_ms": max(
                            b * req.bin_s * 1000,
                            req.scope.start_ms if req.scope.kind == "window" else 0,
                        ),
                        "end_ms": min(
                            (b + 1) * req.bin_s * 1000,
                            req.scope.end_ms
                            if req.scope.kind == "window"
                            else next(
                                int(x["duration_ms"])
                                for x in data["tracking_periods"]
                                if x["period"] == p
                            ),
                        ),
                        "metrics": summary(data, es, req.profile_id, scope=req.scope),
                    }
                    for (p, b), es in sorted(groups.items())
                ]
            }
        raise DomainError("UNREGISTERED_OPERATION", "Operation is not registered.", 404)

    def report_one(self, data, req, kind, entity, profile=None):
        profile = profile or req.profile_id
        team = entity if kind == "team" else None
        player = entity if kind == "player" else None
        if kind == "player":
            record = next(
                (l for l in data["match_lineups"] if l["player_id"] == player), None
            )
            if not record:
                raise DomainError(
                    "ENTITY_NOT_IN_MATCH", "Player is not registered in the match."
                )
            team = record["team_id"]
        elif not any(t["team_id"] == team for t in data["match_teams"]):
            raise DomainError("ENTITY_NOT_IN_MATCH", "Team is not in the match.")
        minutes = self.covered_minutes(data, req.scope, player)
        rows = events_for(data, req, team=team, player=player)
        if profile == "ppda_demo":
            if kind != "team":
                raise DomainError("UNSUPPORTED_METRIC", "ppda_demo is team-only.")
            if (
                req.zone_id != "all"
                or req.score_state != "all"
                or req.pressure != "all"
            ):
                raise DomainError(
                    "UNSUPPORTED_FILTER",
                    "ppda_demo uses its registered zones and all score/pressure states.",
                )
            rows = events_for(data, req, team=None, player=None)
        if profile == "movement":
            if (
                req.zone_id != "all"
                or req.pressure != "all"
                or req.score_state != "all"
            ):
                raise DomainError(
                    "UNSUPPORTED_FILTER",
                    "Movement supports temporal scope and participant filters only.",
                )
            run = self.run(data)
            period, start, end = self.bounds(data, req.scope)
            points = self.repo.movement(
                data["meta"]["match_id"],
                run["run_id"],
                period,
                start,
                end,
                team,
                player,
            )
            metrics = {
                "distance_m": sum(p["distance_m"] for p in points),
                "max_sampled_speed_m_s": max(
                    (p["max_sampled_speed_m_s"] or 0 for p in points), default=0
                ),
                "seconds_above_5_5_m_s": sum(
                    p["seconds_above_5_5_m_s"] for p in points
                ),
                "covered_player_seconds": sum(p["covered_seconds"] for p in points),
            }
        else:
            metrics = summary(data, rows, profile, minutes, team, req.scope)
        if profile == "goalkeeping":
            keeper_intervals = (
                [
                    l
                    for l in data["lineup_positions"]
                    if l["player_id"] == player and l["position_id"] == 1
                ]
                if player is not None
                else []
            )
            if player is not None and not keeper_intervals:
                raise DomainError(
                    "UNSUPPORTED_ENTITY",
                    "Goalkeeping reports require a goalkeeper or team.",
                )

            def clock(text):
                m, s = map(int, text.split(":"))
                return m * 60 + s

            opponent_shots = []
            for e in events_for(data, req, team=None, player=None):
                if e["team_id"] == team or not e["shot"]:
                    continue
                instant = (
                    sum(
                        int(p["duration_ms"]) / 1000
                        for p in data["tracking_periods"]
                        if p["period"] < e["period"]
                    )
                    + e["period_time_ms"] / 1000
                )
                if player is None or any(
                    clock(l["from_time"]) <= instant < clock(l["to_time"])
                    for l in keeper_intervals
                ):
                    opponent_shots.append(e)
            on_target = [
                e
                for e in opponent_shots
                if code(e["shot"]["outcome"]) in (97, 100, 116)
            ]
            saves = sum(code(e["shot"]["outcome"]) in (100, 116) for e in on_target)
            metrics.update(
                saves=saves,
                shots_on_target_faced=len(on_target),
                goals_conceded=sum(code(e["shot"]["outcome"]) == 97 for e in on_target),
                save_rate=ratio(saves, len(on_target)),
                save_definition="On-target opponent shot outcomes, assigned to shot release time; goalkeeper events are separate evidence.",
            )
        return {
            "match_id": data["meta"]["match_id"],
            "entity_kind": kind,
            "entity_id": entity,
            "profile_id": profile,
            "minutes": minutes,
            "metrics": metrics,
        }

    def reports(self, op, req, datasets):
        if op == "compare_entities":
            reports = []
            if req.mode == "entities":
                for id in req.entity_ids:
                    parts = [
                        self.report_one(d, req, req.entity_kind, id) for d in datasets
                    ]
                    reports.append(
                        {
                            "entity_id": id,
                            "matches": parts,
                            "aggregate": self.aggregate_reports(parts),
                        }
                    )
            else:
                for scope in req.windows:
                    variant = req.model_copy(update={"scope": scope})
                    self.validate(datasets[0], variant, entities=False)
                    reports.append(
                        {
                            "scope": scope.model_dump(),
                            "matches": [
                                self.report_one(
                                    datasets[0],
                                    variant,
                                    req.entity_kind,
                                    req.entity_ids[0],
                                )
                            ],
                        }
                    )
            return {"mode": req.mode, "reports": reports, "causal": False}
        if op == "get_rankings":
            profile = RANK_PROFILES[req.metric]
            if req.profile_id != profile:
                raise DomainError(
                    "INVALID_ARGUMENT",
                    f"Metric {req.metric} requires profile_id={profile}.",
                )
            entity_ids = sorted(
                {
                    r["team_id"] if req.entity_kind == "team" else r["player_id"]
                    for d in datasets
                    for r in d["match_lineups"]
                }
            )
            if profile == "goalkeeping" and req.entity_kind == "player":
                keeper_ids = {
                    l["player_id"]
                    for d in datasets
                    for l in d["lineup_positions"]
                    if l["position_id"] == 1
                }
                entity_ids = [id for id in entity_ids if id in keeper_ids]
            rows = []
            for id in entity_ids:
                compatible = [
                    d
                    for d in datasets
                    if any(
                        r["team_id" if req.entity_kind == "team" else "player_id"] == id
                        for r in d["match_lineups"]
                    )
                ]
                parts = [
                    self.report_one(d, req, req.entity_kind, id, profile)
                    for d in compatible
                ]
                minutes = sum(p["minutes"] for p in parts)
                if minutes < req.min_minutes:
                    continue
                total = sum(p["metrics"][req.metric] for p in parts)
                value = (
                    total
                    if req.normalization == "total"
                    else total * 90 / minutes
                    if minutes
                    else None
                )
                rows.append(
                    {
                        "entity_id": id,
                        "minutes": minutes,
                        "matches": len(parts),
                        "total_value": total,
                        "value": value,
                    }
                )
            rows.sort(
                key=lambda r: (r["value"] is None, -(r["value"] or 0), r["entity_id"])
            )
            for i, row in enumerate(rows):
                row["rank"] = i + 1
            revision = ":".join(d["revision"] for d in datasets)
            return {
                **self.page(op, req, rows, revision),
                "metric": req.metric,
                "normalization": req.normalization,
            }
        kind = "team" if op == "get_team_summary" else "player"
        id = req.team_id if kind == "team" else req.player_id
        reports = [self.report_one(d, req, kind, id) for d in datasets]
        return {
            "profile_id": req.profile_id,
            "reports": reports,
            "aggregate": self.aggregate_reports(reports),
            "covered_minutes": sum(r["minutes"] for r in reports),
        }

    def aggregate_reports(self, reports):
        def combine(values, key=""):
            if not values:
                return None
            if isinstance(values[0], dict):
                keys = set().union(*(v.keys() for v in values))
                return {
                    k: combine([v[k] for v in values if k in v], k)
                    for k in sorted(keys)
                }
            if isinstance(values[0], list):
                return [x for v in values for x in v]
            if all(type(v) in (float, int) for v in values):
                return max(values) if key.startswith("max_") else sum(values)
            return values[0]

        result = combine([r["metrics"] for r in reports])
        for field, a, b in [
            ("xg_per_shot", "xg", "shots"),
            ("conversion_rate", "goals", "shots"),
            ("on_target_rate", "shots_on_target", "shots"),
            ("completion_rate", "completed_passes", "attempted_passes"),
            ("dribble_success_rate", "dribbles_complete", "dribble_attempts"),
            (
                "association_rate",
                "pressures_followed_by_recovery_within_5s",
                "eligible_pressures",
            ),
            ("save_rate", "saves", "shots_on_target_faced"),
            (
                "ppda_demo",
                "opponent_regular_pass_attempts_own_60_percent",
                "defensive_actions_opponent_60_percent",
            ),
        ]:
            if a in result and b in result:
                result[field] = ratio(result[a], result[b])
        return result

    def tracking(self, op, req, data):
        if op == "get_event_context":
            event = data["event_index"][str(req.event_id)]
            links = [
                l
                for l in data["event_tracking_links"]
                if l["event_id"] == str(req.event_id)
            ]
            if len(links) != 1:
                raise DomainError(
                    "RUN_AMBIGUOUS", "Event requires one tracking alignment."
                )
            run = self.run(data, links[0]["run_id"])
            duration = next(
                int(p["duration_ms"])
                for p in data["tracking_periods"]
                if p["period"] == event["period"]
            )
            start = max(0, event["period_time_ms"] - req.before_s * 1000)
            end = min(duration + 1, event["period_time_ms"] + req.after_s * 1000 + 1)
            frames = self.repo.tracking(
                data["meta"]["match_id"], run["run_id"], event["period"], start, end
            )
            relations = [
                r
                for r in data["event_relations"]
                if str(req.event_id) in (r["event_id"], r["related_event_id"])
            ]
            return {
                "event": event,
                "pass": data["passes"].get(str(req.event_id)),
                "shot": data["shots"].get(str(req.event_id)),
                "relations": relations,
                "related_events": [
                    data["event_index"][id]
                    for id in sorted(
                        {r["event_id"] for r in relations}
                        | {r["related_event_id"] for r in relations}
                    )
                    if id != str(req.event_id)
                ],
                "frames": frames,
                "run_id": run["run_id"],
                "freeze_players": [
                    p
                    for p in data["shot_freeze_players"]
                    if p["event_id"] == str(req.event_id)
                ],
                "frame_360": [
                    f for f in data["frames_360"] if f["event_id"] == str(req.event_id)
                ],
                "anonymous_360_players": [
                    p
                    for p in data["frame_360_players"]
                    if p["event_id"] == str(req.event_id)
                ],
                "_coverage": self.tracking_coverage(
                    frames, run, expected=max(0, (end - 1 - start) // 1000 + 1)
                ),
            }
        run = self.run(data, req.run_id)
        if op == "get_tracking_frame":
            period, start, end, stride = req.period, req.time_ms, req.time_ms + 1, 1
        else:
            period, start, end, stride = (
                req.scope.period,
                req.scope.start_ms,
                req.scope.end_ms,
                req.stride_s,
            )
            if end - start > 120000:
                raise DomainError(
                    "WINDOW_TOO_LARGE", "Tracking windows are limited to 120 seconds."
                )
        duration = next(
            int(p["duration_ms"])
            for p in data["tracking_periods"]
            if p["period"] == period
        )
        if (
            start % 1000
            or (op == "get_tracking_window" and end % 1000)
            or start > duration
            or end > duration + (1 if op == "get_tracking_frame" else 0)
        ):
            raise DomainError(
                "INVALID_ARGUMENT", "Tracking requires sampled seconds within a period."
            )
        frames = self.repo.tracking(
            req.match_id,
            run["run_id"],
            period,
            start,
            end,
            stride,
            getattr(req, "team_id", None),
            getattr(req, "player_id", None),
        )
        expected = (end - start + stride * 1000 - 1) // (stride * 1000)
        return {
            "run_id": run["run_id"],
            "frames": frames,
            "_coverage": self.tracking_coverage(frames, run, expected),
        }

    def tracking_coverage(self, frames, run, expected):
        valid = sum(
            bool(f["ball"]) and f["ball"]["position_status"] == "available"
            for f in frames
        )
        return {
            "run_id": run["run_id"],
            "expected_samples": expected,
            "returned_samples": len(frames),
            "valid_ball_samples": valid,
            "coverage_ratio": ratio(valid, expected),
            "player_position_rows": sum(len(f["players"]) for f in frames),
            "sample_rate_hz": run["sample_rate_hz"],
        }

    def aggregates(self, op, req, data):
        if req.team_id is None and req.player_id is None:
            raise DomainError("INVALID_ARGUMENT", "Select a team or player.")
        run = self.run(data)
        period, start, end = self.bounds(data, req.scope)
        if op == "get_movement_summary":
            return {
                "players": self.repo.movement(
                    req.match_id,
                    run["run_id"],
                    period,
                    start,
                    end,
                    req.team_id,
                    req.player_id,
                ),
                "run_id": run["run_id"],
                "method": "Adjacent available samples at 1Hz, separated by player and period.",
            }
        if op == "get_heatmap" and req.mode == "event_count":
            rows = events_for(data, req)
            if req.event_type != "all":
                rows = [e for e in rows if e["type_id"] == EVENT_TYPES[req.event_type]]
            size = int(req.grid_id[:-1])
            cells = Counter(
                (
                    min(
                        int(e["attacking_x_m"] // size) * size,
                        int((105 - 1e-9) // size) * size,
                    ),
                    min(
                        int(e["attacking_y_m"] // size) * size,
                        int((68 - 1e-9) // size) * size,
                    ),
                )
                for e in rows
                if e["attacking_x_m"] is not None
            )
            return {
                "cells": [
                    {"x_m": x, "y_m": y, "events": n}
                    for (x, y), n in sorted(cells.items())
                ],
                "mode": "event_count",
                "orientation": "acting_team_attacking_metres",
            }
        if op == "get_heatmap" and (
            req.zone_id != "all"
            or req.score_state != "all"
            or req.pressure != "all"
            or req.event_type != "all"
        ):
            raise DomainError(
                "UNSUPPORTED_FILTER",
                "Occupancy heatmap supports temporal and participant filters. Use event_count for action filters.",
            )
        grid = int(req.grid_id[:-1]) if op == "get_heatmap" else 105
        zone = req.zone_id if op == "get_zone_summary" else "all"
        cells = self.repo.occupancy(
            req.match_id,
            run["run_id"],
            period,
            start,
            end,
            req.team_id,
            req.player_id,
            grid,
            op == "get_zone_summary",
            ZONES[zone],
        )
        if op == "get_zone_summary":
            rows = events_for(data, req)
            return {
                "zone_id": zone,
                "bounds_attacking_metres": ZONES[zone],
                "player_seconds_in_zone": sum(c["seconds_in_zone"] for c in cells),
                "sampled_entries": sum(c["entries"] for c in cells),
                "valid_player_seconds": sum(c["valid_seconds"] for c in cells),
                "event_counts": dict(Counter(e["type_name"] for e in rows)),
                "xg": sum(e["shot"]["statsbomb_xg"] or 0 for e in rows if e["shot"]),
                "entry_method": "Change from outside to inside between consecutive valid 1Hz samples; no boundary interpolation.",
            }
        return {
            "cells": cells,
            "mode": "occupancy_seconds",
            "orientation": "fixed_pitch_metres",
            "grid_m": grid,
            "total_player_seconds": sum(c["seconds_in_zone"] for c in cells),
        }

    def spatial(self, op, req, data):
        allowed_views = {
            "get_proximity_connectivity": {"summary", "geometry", "matrix"},
            "get_space_coverage": {"summary", "geometry", "triangulation"},
        }.get(op, {"summary", "geometry"})
        if req.view not in allowed_views:
            raise DomainError(
                "INVALID_ARGUMENT", "View is not supported by this spatial operation."
            )
        if req.epsilon_m != 15 and op not in (
            "get_proximity_connectivity",
            "get_node_removal_robustness",
        ):
            raise DomainError(
                "INVALID_ARGUMENT", "This operation uses a fixed scale profile."
            )
        if op == "get_passing_network" and (
            req.event_id or req.period is not None or req.time_ms is not None
        ):
            raise DomainError(
                "INVALID_ARGUMENT",
                "Passing network uses a temporal scope, not a snapshot selector.",
            )
        run = self.run(data, req.run_id)
        rows = events_for(data, req, team=None, player=None)
        if op == "get_passing_network":
            node_ids = {
                l["player_id"]
                for l in data["match_lineups"]
                if l["team_id"] == req.team_id
                and self.covered_minutes(data, req.scope, l["player_id"]) > 0
            }
            return topology.passing_network(data, rows, req.team_id, node_ids)
        if op in ("get_line_breaks", "get_defensive_profile"):
            return self.spatial_episodes(op, req, data, run, rows)
        if req.event_id:
            event = data["event_index"].get(str(req.event_id))
            if not event:
                raise DomainError(
                    "EVENT_NOT_FOUND", "Event does not belong to the match.", 404
                )
            if (
                req.period is not None
                or req.time_ms is not None
                or req.scope.kind != "match"
            ):
                raise DomainError(
                    "INVALID_ARGUMENT",
                    "Use event_id or a temporal selection, not both.",
                )
            frames = self.repo.anchor_tracking(run["run_id"], [event["event_id"]])
        elif req.period is not None and req.time_ms is not None:
            if req.scope.kind != "match":
                raise DomainError(
                    "INVALID_ARGUMENT", "Use a snapshot or a scope, not both."
                )
            point = c.TrackingFrame(
                match_id=req.match_id,
                run_id=req.run_id,
                period=req.period,
                time_ms=req.time_ms,
            )
            frames = self.tracking("get_tracking_frame", point, data)["frames"]
        elif req.scope.kind == "window":
            if req.scope.end_ms - req.scope.start_ms > 60000:
                raise DomainError(
                    "WINDOW_TOO_LARGE",
                    "Spatial series are limited to 60 sampled frames.",
                )
            window = c.TrackingWindow(
                match_id=req.match_id, run_id=req.run_id, scope=req.scope
            )
            frames = self.tracking("get_tracking_window", window, data)["frames"]
        else:
            raise DomainError(
                "INVALID_ARGUMENT",
                "Select event_id, period/time_ms, or a window of at most 60 seconds.",
            )
        if not frames:
            raise DomainError(
                "INSUFFICIENT_COVERAGE", "No tracking samples for this selection."
            )
        output = []
        for frame in frames:
            players = self.with_roles(data, frame)
            selected = topology.cloud(players, req.team_id)
            if op == "get_team_shape":
                result = topology.shape(selected)
            elif op == "get_proximity_connectivity":
                result = topology.proximity(
                    selected, req.epsilon_m, req.view == "matrix"
                )
            elif op == "get_space_coverage":
                result = topology.coverage(
                    topology.cloud(players, outfield=False),
                    run["pitch_length_m"],
                    run["pitch_width_m"],
                    req.view == "triangulation",
                )
            elif op == "get_persistent_structure":
                result = topology.persistence(selected)
            elif op == "get_node_removal_robustness":
                result = topology.robustness(selected, req.epsilon_m)
            elif op == "get_pass_corridor":
                if not req.event_id or len(frames) != 1:
                    raise DomainError(
                        "INVALID_ARGUMENT",
                        "Pass corridor requires one registered pass event_id.",
                    )
                event = data["event_index"][str(req.event_id)]
                p = data["passes"].get(event["event_id"])
                if not p or code(p["height"]) != 1:
                    raise DomainError(
                        "UNSUPPORTED_GEOMETRY",
                        "Corridor supports registered ground passes only.",
                    )
                if req.team_id != event["team_id"]:
                    raise DomainError(
                        "INVALID_ARGUMENT", "Select the passing team for pass corridor."
                    )
                start = self.to_fixed(
                    data, event, event["location_x"], event["location_y"], run
                )
                end = self.to_fixed(data, event, p["end_x"], p["end_y"], run)
                opponents = [
                    p
                    for p in players
                    if p["team_id"] != event["team_id"]
                    and p["position_status"] == "available"
                ]
                result = topology.corridor(start, end, opponents)
            else:
                raise DomainError(
                    "UNREGISTERED_OPERATION", "Spatial operation is not registered."
                )
            output.append(
                {
                    "period": frame["period"],
                    "time_ms": frame["period_time_ms"],
                    "result": result,
                }
            )
        return {
            "samples": output,
            "run_id": run["run_id"],
            "_coverage": self.tracking_coverage(frames, run, len(frames)),
        }

    def with_roles(self, data, frame):
        result = []
        periods = {
            p["period"]: int(p["duration_ms"]) / 1000 for p in data["tracking_periods"]
        }
        clock = (
            sum(t for p, t in periods.items() if p < frame["period"])
            + frame["period_time_ms"] / 1000
        )

        def seconds(text):
            m, s = map(int, text.split(":"))
            return m * 60 + s

        expected = {
            l["player_id"]
            for l in data["lineup_positions"]
            if seconds(l["from_time"]) <= clock
            and (
                clock < seconds(l["to_time"])
                or clock == sum(periods.values()) == seconds(l["to_time"])
            )
        }
        available = {
            p["player_id"]
            for p in frame["players"]
            if p["position_status"] == "available"
            and p["x_m"] is not None
            and p["y_m"] is not None
        }
        if expected != available:
            raise DomainError(
                "INSUFFICIENT_COVERAGE",
                "Spatial analysis requires positions for every active participant.",
            )
        for p in frame["players"]:
            intervals = [
                l
                for l in data["lineup_positions"]
                if l["player_id"] == p["player_id"]
                and seconds(l["from_time"]) <= clock <= seconds(l["to_time"])
            ]
            role = intervals[-1]["position_id"] if intervals else None
            result.append({**p, "role_id": role, "is_goalkeeper": role == 1})
        return result

    def to_fixed(self, data, event, x, y, run):
        home = next(t["team_id"] for t in data["match_teams"] if t["side"] == "home")
        positive = next(
            p["home_attacks_positive_x"]
            for p in data["tracking_periods"]
            if p["run_id"] == run["run_id"] and p["period"] == event["period"]
        ) == (event["team_id"] == home)
        x, y = x * run["pitch_length_m"] / 120, y * run["pitch_width_m"] / 80
        return (
            [x, y]
            if positive
            else [run["pitch_length_m"] - x, run["pitch_width_m"] - y]
        )

    def spatial_episodes(self, op, req, data, run, rows):
        if req.period is not None or req.time_ms is not None:
            raise DomainError(
                "INVALID_ARGUMENT", "Episode analysis uses scope or event_id."
            )
        if op == "get_line_breaks":
            anchors = [
                e
                for e in rows
                if e["team_id"] == req.team_id
                and e["pass"]
                and e["pass"]["outcome"] is None
            ]
        else:
            anchors = [
                e
                for e in rows
                if e["team_id"] != req.team_id and e["type_id"] in (16, 30)
            ]
        if req.event_id:
            anchors = [e for e in anchors if e["event_id"] == str(req.event_id)]
            if not anchors:
                raise DomainError(
                    "INVALID_ARGUMENT",
                    "Event is not a compatible action anchor for this team.",
                )
        if len(anchors) > 1000:
            raise DomainError(
                "WINDOW_TOO_LARGE", "Choose a scope with at most 1000 action anchors."
            )
        if not anchors:
            return {
                "anchor_count": 0,
                "samples": [],
                "phase_evidence": "opponent_pass_or_shot"
                if op == "get_defensive_profile"
                else "completed_pass",
            }
        frames = self.repo.anchor_tracking(
            run["run_id"], [e["event_id"] for e in anchors]
        )
        lookup = {(f["period"], f["period_time_ms"]): f for f in frames}
        samples = []
        for event in anchors:
            frame = lookup.get((event["period"], event["period_time_ms"]))
            if not frame:
                raise DomainError(
                    "INSUFFICIENT_COVERAGE", "Missing tracking for an action anchor."
                )
            players = self.with_roles(data, frame)
            if op == "get_line_breaks":
                p = event["pass"]
                origin, end = event["location_x"] * 105 / 120, p["end_x"] * 105 / 120
                ref0 = self.to_fixed(data, event, 0, 0, run)
                positive = ref0[0] == 0
                opponents = [
                    p
                    for p in players
                    if p["team_id"] != req.team_id
                    and p["position_status"] == "available"
                ]
                groups = {
                    "defense": {2, 3, 4, 5, 6, 7, 8},
                    "midfield": set(range(9, 17)),
                    "attack": set(range(17, 26)),
                }
                lines = []
                for name, roles in groups.items():
                    ps = [p for p in opponents if p["role_id"] in roles]
                    if len(ps) < 2:
                        continue
                    xs = sorted(p["x_m"] if positive else 105 - p["x_m"] for p in ps)
                    mid = len(xs) // 2
                    line = xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2
                    if origin < line - 1 and end > line + 1:
                        lines.append(
                            {
                                "line": name,
                                "reference_x_m": line,
                                "player_ids": [p["player_id"] for p in ps],
                            }
                        )
                if lines:
                    samples.append(
                        {
                            "event_id": event["event_id"],
                            "period": event["period"],
                            "time_ms": event["period_time_ms"],
                            "lines_crossed": lines,
                        }
                    )
            else:
                selected = topology.cloud(players, req.team_id)
                geometry = topology.shape(selected)
                graph = topology.proximity(selected, 15)
                from shapely.geometry import MultiPoint, Point

                hull = MultiPoint([(p["x_m"], p["y_m"]) for p in selected]).convex_hull
                opponents = [
                    p
                    for p in players
                    if p["team_id"] != req.team_id
                    and p["position_status"] == "available"
                ]
                sample = {
                    "event_id": event["event_id"],
                    "period": event["period"],
                    "time_ms": event["period_time_ms"],
                    "width_m": geometry["width_m"],
                    "length_m": geometry["length_m"],
                    "hull_area_m2": geometry["hull_area_m2"],
                    "component_count_15m": graph["component_count"],
                    "critical_connection_distance_m": graph[
                        "critical_connection_distance_m"
                    ],
                    "opponents_inside_hull": sum(
                        hull.covers(Point(p["x_m"], p["y_m"])) for p in opponents
                    ),
                }
                defenders = [
                    p
                    for p in players
                    if p["team_id"] == req.team_id
                    and p["position_status"] == "available"
                ]
                if frame["ball"] and frame["ball"]["position_status"] == "available":
                    sample["nearest_defender_to_ball_m"] = min(
                        hypot(
                            p["x_m"] - frame["ball"]["x_m"],
                            p["y_m"] - frame["ball"]["y_m"],
                        )
                        for p in defenders
                    )
                if event["pass"] and code(event["pass"]["height"]) == 1:
                    start = self.to_fixed(
                        data, event, event["location_x"], event["location_y"], run
                    )
                    end = self.to_fixed(
                        data, event, event["pass"]["end_x"], event["pass"]["end_y"], run
                    )
                    if hypot(end[0] - start[0], end[1] - start[1]) > 1e-6:
                        passage = topology.corridor(start, end, defenders)
                        sample["defenders_in_ground_pass_corridor"] = passage[
                            "opponents_in_corridor"
                        ]
                        sample["nearest_defender_to_pass_m"] = passage[
                            "nearest_opponent_distance_m"
                        ]
                samples.append(sample)
        conceded = [e for e in rows if e["team_id"] != req.team_id and e["shot"]]
        return {
            "anchor_count": len(anchors),
            "samples": samples,
            "phase_evidence": "opponent_pass_or_shot"
            if op == "get_defensive_profile"
            else "completed_pass",
            "shots_conceded": len(conceded),
            "xg_conceded": sum(e["shot"]["statsbomb_xg"] or 0 for e in conceded),
            "impenetrability_score": None,
            "_coverage": {"anchors": len(anchors), "aligned_frames": len(frames)},
        }
