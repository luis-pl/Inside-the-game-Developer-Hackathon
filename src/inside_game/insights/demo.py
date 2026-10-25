"""Galería de componentes con fixture SINTÉTICO ilustrativo, no un partido real.

El escenario pequeño sirve para recorrer las treinta recetas sin pedir modelo,
SQL ni red. Las posiciones y acciones son ejemplos de interfaz, no evidencia
de realismo futbolístico ni una nueva carga de la base de datos.
"""

import argparse
import json
from pathlib import Path

from inside_game.tools import topology

from .catalog import RECIPES
from .pages import render_report


def demo_manifest():
    positions = [(5, 34), (24, 20), (25, 48), (45, 25), (44, 45), (68, 30), (75, 42)]
    frames = []
    for t in range(7):
        players = []
        for team in (1, 2):
            for j, (x, y) in enumerate(positions):
                players.append(
                    {
                        "player_id": team * 100 + j,
                        "team_id": team,
                        "x_m": x + t * 0.2 if team == 1 else 105 - x - t * 0.1,
                        "y_m": y,
                        "position_status": "available",
                        "is_on_pitch": True,
                        "is_goalkeeper": j == 0,
                        "on_pitch_slot": j + 1,
                    }
                )
        frames.append(
            {
                "period": 1,
                "period_time_ms": 10000 + t * 1000,
                "ball_in_play": True,
                "players": players,
                "ball": None
                if t == 2
                else {"x_m": 40 + t * 2, "y_m": 30, "position_status": "available"},
            }
        )

    def event(i, type_id, team, time, x=45, y=25, **fields):
        return {
            "event_id": f"fixture-{i}",
            "period": 1,
            "period_time_ms": time,
            "event_index": i,
            "type_id": type_id,
            "type_name": {
                30: "Pass",
                16: "Shot",
                17: "Pressure",
                3: "Dispossessed",
                2: "Recovery",
                42: "Receipt",
                43: "Carry",
            }.get(type_id, "Action"),
            "team_id": team,
            "player_id": team * 100 + 3,
            "location_x": x * 120 / 105,
            "location_y": y * 80 / 68,
            "duration": 1.0,
            **fields,
        }

    events = [
        event(
            1,
            30,
            1,
            11000,
            **{
                "pass": {
                    "end_x": 68 * 120 / 105,
                    "end_y": 30 * 80 / 68,
                    "recipient_player_id": 105,
                    "outcome": None,
                }
            },
        ),
        event(
            2,
            16,
            1,
            11500,
            shot={"statsbomb_xg": 0.15, "outcome": {"id": 100, "name": "Saved"}},
        ),
        event(3, 3, 1, 12000),
        event(
            4,
            30,
            2,
            13000,
            **{
                "pass": {
                    "end_x": 70,
                    "end_y": 30,
                    "recipient_player_id": 204,
                    "outcome": None,
                }
            },
        ),
        event(5, 17, 1, 14000),
        event(6, 3, 2, 14500),
        event(7, 2, 1, 15000),
        event(8, 42, 1, 16000),
        event(9, 43, 1, 10000, x=55, carry={"end_x": 85, "end_y": 32, "outcome": None}),
        event(
            10,
            16,
            2,
            13500,
            shot={"statsbomb_xg": 0.3, "outcome": {"id": 98, "name": "Off Target"}},
        ),
    ]
    evidence = []
    bindings = {}

    def add(op, data, **args):
        eid = f"e{len(evidence) + 1}"
        qid = f"q{len(evidence) + 1}"
        arguments = {
            "match_id": 900001,
            "scope": {
                "kind": "window",
                "period": 1,
                "start_ms": 10000,
                "end_ms": 17000,
            },
            **args,
        }
        evidence.append(
            {
                "evidence_id": eid,
                "query_id": qid,
                "operation": op,
                "arguments": arguments,
                "response": {
                    "operation_id": op,
                    "method_id": op + "_fixture_v1",
                    "request_id": "component-fixture",
                    "scope": arguments,
                    "data": data,
                    "provenance": {
                        "is_synthetic": True,
                        "provider": "UI component fixture",
                        "demo_fixture_only": True,
                    },
                    "coverage": {
                        "returned_samples": 7,
                        "note": "14 players: reduced illustrative fixture, not a full professional match",
                    },
                    "coordinates": {
                        "events": "acting_team_120x80",
                        "tracking": "fixed_105x68_m",
                    },
                    "pagination": {"next_cursor": None},
                    "warnings": [
                        "SINTÉTICO: fixture ilustrativo de componentes con 14 jugadores; no representa un partido de Azure ni un Mundial."
                    ],
                },
            }
        )
        bindings.setdefault(op, []).append(eid)

    add("get_tracking_window", {"frames": frames}, sample_step_ms=1000)
    add("get_tracking_frame", {"frames": [frames[0]]}, period=1, time_ms=10000)
    add("get_match_context", {"match": {"match_id": 900001}, "lineups": []})
    for op, ids in [
        ("get_shots", {16}),
        ("get_passes", {30}),
        ("get_defensive_actions", {2, 17}),
        ("get_ball_actions", {43}),
        ("get_events", {e["type_id"] for e in events}),
    ]:
        items = [e for e in events if e["type_id"] in ids]
        add(
            op,
            {
                "items": items,
                "total": len(items),
                "summary": {"observed_events": len(items)},
            },
            team_id=None,
            event_types=[],
        )
    add(
        "get_heatmap",
        {
            "cells": [
                {"cell_x_m": x, "cell_y_m": y, "seconds_in_zone": n}
                for x, y, n in [(40, 25, 2), (45, 25, 4), (45, 30, 1)]
            ],
            "mode": "occupancy_seconds",
        },
        grid_id="5m",
    )
    add(
        "get_movement_summary",
        {
            "players": [
                {"player_id": 103, "distance_m": 1.2, "covered_seconds": 6},
                {"player_id": 104, "distance_m": 1.2, "covered_seconds": 6},
            ]
        },
    )
    add(
        "get_zone_summary",
        {"zone_id": "final_third", "player_seconds_in_zone": 7, "sampled_entries": 1},
    )
    add(
        "get_metric_series",
        {
            "series": [
                {"period": 1, "start_ms": 10000, "metrics": {"shots": 1}},
                {"period": 1, "start_ms": 13000, "metrics": {"shots": 1}},
            ]
        },
    )
    for op in ["get_sequences", "get_possessions", "get_set_piece_sequences"]:
        add(
            op,
            {
                "items": [
                    {
                        "label": "Cadena ilustrativa",
                        "event_ids": ["fixture-1", "fixture-2"],
                        "period": 1,
                    }
                ]
            },
        )
    add(
        "compare_entities",
        {
            "reports": [
                {"entity_id": 103, "metrics": {"distance_m": 1.2}},
                {"entity_id": 104, "metrics": {"distance_m": 1.2}},
            ]
        },
    )
    own = [
        p for p in frames[0]["players"] if p["team_id"] == 1 and not p["is_goalkeeper"]
    ]
    for op, data in [
        ("get_team_shape", topology.shape(own)),
        ("get_proximity_connectivity", topology.proximity(own)),
        ("get_space_coverage", topology.coverage(frames[0]["players"])),
        ("get_persistent_structure", topology.persistence(own)),
        ("get_node_removal_robustness", topology.robustness(own)),
    ]:
        add(op, {"samples": [{"period": 1, "time_ms": 10000, "result": data}]})
    add(
        "get_passing_network",
        {
            "edges": [
                {"source": 101, "target": 103, "passes": 3},
                {"source": 103, "target": 105, "passes": 3},
                {"source": 105, "target": 101, "passes": 3},
            ],
            "nodes": [{"player_id": i} for i in [101, 103, 105]],
        },
    )
    add(
        "get_defensive_profile",
        {
            "samples": [
                {
                    "period": 1,
                    "time_ms": 10000,
                    "result": {"opponent_actions": 2, "components": 2},
                }
            ]
        },
    )
    parameters = {
        "team_id": 1,
        "period": 1,
        "time_ms": 10000,
        "attack_positive_x": True,
        "defender_ids": [101, 102],
        "midfielder_ids": [103, 104],
        "goalkeeper_id": 100,
    }
    for e in evidence:
        if e["operation"] in {
            "get_metric_series",
            "get_heatmap",
            "get_movement_summary",
            "get_zone_summary",
            "get_passing_network",
        }:
            e["arguments"]["team_id"] = 1
    blocks = []
    for key, recipe in RECIPES.items():
        chosen = list(
            dict.fromkeys(
                eid
                for op in recipe["source_operations"]
                for eid in bindings.get(op, [])
            )
        )
        # Las recetas derivadas necesitan tracking además de acciones.
        if key in {"between_lines_receptions", "structural_pass"}:
            chosen = list(dict.fromkeys(chosen + bindings["get_tracking_window"]))
        params = {**parameters}
        if key == "between_lines_receptions":
            params.update(defender_ids=[201, 202], midfielder_ids=[203, 204])
        if key == "ball_recovery_time":
            params.pop("time_ms")
        blocks.append(
            {"id": key, "insight_id": key, "evidence_ids": chosen, "parameters": params}
        )
    return {
        "title": "Biblioteca de 30 insights · escenario sintético ilustrativo",
        "blocks": blocks,
        "evidence": evidence,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path(".temp/insights/gallery.html")
    )
    args = parser.parse_args()
    manifest = demo_manifest()
    result = render_report(manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result.pop("html"), encoding="utf-8")
    args.output.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    args.output.with_suffix(".verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "render_ms": result["render_ms"],
                "bytes": result["bytes"],
                "states": {b["id"]: b["state"] for b in result["blocks"]},
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
