"""Compone un informe desde la API deportiva con consultas cerradas.

No ejecuta modelos. Las credenciales se leen en el servidor desde la configuración
privada existente; nunca se escriben en el manifiesto ni en el HTML exportado.
"""

import argparse
import json
import time
from pathlib import Path

import httpx

from inside_game.agents.contracts import Evidence
from inside_game.contracts import ApiResponse
from inside_game.dashboard.config import DashboardConfig
from inside_game.insights.pages import render_report
from inside_game.service import OPERATIONS


class ReportSource:
    """Bounded, typed API client; redirects never receive the bearer token."""

    def __init__(self, client):
        self.client = client
        self.evidence = []

    def fetch(self, operation, arguments):
        query_id = f"q{len(self.evidence) + 1}"
        ids, cursors = [], set()
        for page in range(30):
            checked = (
                OPERATIONS[operation].model_validate(arguments).model_dump(mode="json")
            )
            response = self.client.post(f"/api/operations/{operation}", json=checked)
            if response.status_code != 200:
                raise ValueError(
                    f"{operation}: HTTP {response.status_code}; no se exportó un informe incompleto."
                )
            result = ApiResponse.model_validate(response.json())
            if result.operation_id != operation:
                raise ValueError(
                    "La respuesta no coincide con la operación solicitada."
                )
            evidence = Evidence(
                evidence_id=f"{query_id}-p{page + 1}",
                query_id=query_id,
                operation=operation,
                arguments=checked,
                response=result,
            )
            self.evidence.append(evidence.model_dump(mode="json"))
            ids.append(evidence.evidence_id)
            cursor = result.pagination.get("next_cursor")
            if not cursor:
                return ids
            if cursor in cursors:
                raise ValueError("Cursor de paginación repetido.")
            cursors.add(cursor)
            arguments = {**arguments, "cursor": cursor}
        raise ValueError("Presupuesto de paginación agotado.")


def build(source, match_id):
    context = source.fetch("get_match_context", {"match_id": match_id})
    match = source.evidence[0]["response"]["data"]["match"]
    home, away = match["home_team_id"], match["away_team_id"]
    names = {home: match["home_team_name"], away: match["away_team_name"]}
    common = {"match_id": match_id}
    first_half = {"kind": "period", "period": 1}
    episode = {"kind": "window", "period": 1, "start_ms": 590000, "end_ms": 610000}
    blocks = []

    def block(key, title, ids, parameters=None, span="half"):
        blocks.append(
            {
                "id": f"block{len(blocks) + 1}",
                "insight_id": key,
                "title": title,
                "evidence_ids": ids,
                "parameters": parameters or {},
                "visual": {
                    "span": span,
                    "min_edge_weight": 3 if key == "passing_network" else 1,
                },
            }
        )

    shots = source.fetch("get_shots", {**common, "limit": 200})
    block(
        "shot_map", "De dónde llegaron los tiros · partido completo", shots, span="full"
    )
    block("xg_story", "Cuándo se acumuló el xG · partido completo", shots, span="full")
    possessions = source.fetch("get_possessions", {**common, "limit": 200})
    block(
        "sequence_explorer",
        "El ritmo de las posesiones registradas",
        possessions,
        span="full",
    )
    networks, pass_evidence = {}, {}
    for key in (home, away):
        params = {"team_id": key, "period": 1}
        passes = source.fetch(
            "get_passes", {**common, "team_id": key, "scope": first_half, "limit": 200}
        )
        network = source.fetch(
            "get_passing_network",
            {**common, "team_id": key, "scope": first_half, "view": "geometry"},
        )
        networks[key], pass_evidence[key] = network, passes
        block(
            "passing_network",
            f"Conexiones · {names[key]} · P1",
            network + passes,
            params,
        )
        block("pass_map", f"Trayectorias de pase · {names[key]} · P1", passes, params)
        heat = source.fetch(
            "get_heatmap",
            {**common, "team_id": key, "scope": episode, "grid_id": "5m", "limit": 200},
        )
        block(
            "occupation_heatmap",
            f"Ocupación · {names[key]} · P1 9:50–10:10",
            heat,
            {"team_id": key},
        )
    # Pair the same visual family across teams so comparisons share a row.
    order = {"passing_network": 0, "pass_map": 1, "occupation_heatmap": 2}
    blocks[3:] = sorted(blocks[3:], key=lambda b: order[b["insight_id"]])
    frame = source.fetch(
        "get_tracking_frame", {**common, "period": 1, "time_ms": 600000}
    )
    coverage = source.fetch(
        "get_space_coverage",
        {**common, "team_id": home, "period": 1, "time_ms": 600000, "view": "geometry"},
    )
    block(
        "space_partition",
        "El espacio entre los jugadores · P1 10:00",
        coverage + frame,
        {"period": 1, "time_ms": 600000},
        "full",
    )
    shape = source.fetch(
        "get_team_shape",
        {**common, "team_id": home, "period": 1, "time_ms": 600000, "view": "geometry"},
    )
    block(
        "team_shape",
        f"Estructura · {names[home]} · P1 10:00",
        shape + frame,
        {"team_id": home, "period": 1, "time_ms": 600000},
    )
    tracking = source.fetch(
        "get_tracking_window", {**common, "scope": episode, "sample_step_ms": 1000}
    )
    block(
        "play_replay",
        "La jugada en movimiento · P1 9:50–10:10",
        tracking + context,
        {"period": 1},
    )
    persistent = source.fetch(
        "get_persistent_structure",
        {**common, "team_id": home, "period": 1, "time_ms": 600000, "view": "geometry"},
    )
    block(
        "persistent_structure",
        f"Conexiones a distintas distancias · {names[home]}",
        persistent,
        {"team_id": home, "period": 1, "time_ms": 600000},
    )
    block(
        "hodge_flow",
        f"Cómo se distribuye el flujo neto · {names[home]} · P1",
        networks[home],
        {"team_id": home},
    )
    line_breaks = source.fetch(
        "get_line_breaks",
        {**common, "team_id": home, "scope": first_half, "view": "geometry"},
    )
    block(
        "defensive_geometry",
        f"Pases que cruzan líneas · {names[home]} · P1",
        line_breaks + pass_evidence[home],
        {"team_id": home, "period": 1},
        "full",
    )
    return {
        "title": "Un partido, varias formas de leerlo",
        "template_id": "match_overview",
        "teams": [
            {"team_id": home, "color": "#2463bc"},
            {"team_id": away, "color": "#bf402e"},
        ],
        "blocks": blocks,
        "evidence": source.evidence,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--match-id", type=int, default=900001)
    parser.add_argument(
        "--output", type=Path, default=Path(".temp/insights/match-900001.html")
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    config = DashboardConfig.load(root)
    started = time.perf_counter()
    with httpx.Client(
        base_url=config.api_url,
        headers={"Authorization": f"Bearer {config.api_key}"},
        timeout=60,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        manifest = build(ReportSource(client), args.match_id)
    fetched = time.perf_counter() - started
    rendered = render_report(manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered.pop("html"), encoding="utf-8")
    args.output.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    result = {
        "match_id": args.match_id,
        "api_seconds": round(fetched, 2),
        "api_responses": len(manifest["evidence"]),
        **rendered,
    }
    args.output.with_suffix(".verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
