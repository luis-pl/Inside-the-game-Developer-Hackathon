"""QA real opcional: Beam Free -> insights HTTP -> data HTTP -> MCP -> SQL.

Requiere el servicio de agentes activo. Guarda resultados y HTML sin secretos.
Cinco solicitudes: tres páginas distintas, una ampliación y un cambio de estilo.
No compra crédito ni modifica proveedor. Aborta si no está activo free-only Go.
"""

import argparse
import json
import os
import time
from html.parser import HTMLParser
from pathlib import Path
from uuid import uuid4

import httpx

from inside_game.agents_cli import load_local_env
from inside_game.tools.mcp_client import DataMcpSettings


class PayloadParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reading, self.payload = False, ""

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("id") == "report-data":
            self.reading = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.reading = False

    def handle_data(self, data):
        if self.reading:
            self.payload += data


def run(args):
    root = Path(__file__).resolve().parents[1]
    load_local_env(root)
    if not (
        os.getenv("INSIDE_GAME_MODEL_PROVIDER") == "opencode-go"
        and os.getenv("INSIDE_GAME_OPENCODE_MODEL") == "beam-free"
        and os.getenv("INSIDE_GAME_OPENCODE_FREE_ONLY") == "1"
    ):
        raise ValueError("QA_REQUIRES_VERIFIED_FREE_ONLY_BEAM_GO")
    key = DataMcpSettings.from_env().key
    folder = args.output_dir
    folder.mkdir(parents=True, exist_ok=True)
    records = []
    with httpx.Client(
        base_url=args.base_url,
        headers={"Authorization": "Bearer " + key},
        timeout=60,
        trust_env=False,
        follow_redirects=False,
    ) as client:

        def execute(name, request):
            started = time.perf_counter()
            response = client.post(
                "/a2a/v1/insights", json={"request_id": str(uuid4()), **request}
            )
            payload = response.json()
            wall = round(time.perf_counter() - started, 3)
            (folder / f"{name}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            record = {
                "case": name,
                "http": response.status_code,
                "wall_seconds": wall,
                "status": payload.get("status"),
                "issues": payload.get("issues", []),
                "blocks": payload.get("blocks", []),
                "tool_trace": payload.get("tool_trace", []),
                "model_turns": payload.get("model_turns"),
                "total_tokens": payload.get("total_tokens"),
                "timings_ms": payload.get("timings_ms", {}),
                "revision": payload.get("revision"),
                "data_runs": payload.get("data_runs", []),
            }
            records.append(record)
            print(json.dumps(record, ensure_ascii=True), flush=True)
            if response.status_code != 200 or not payload.get("artifact_url"):
                return payload, None, None
            artifact = client.get(payload["artifact_url"])
            artifact.raise_for_status()
            html = artifact.text
            if key in html:
                raise ValueError("CREDENTIAL_IN_ARTIFACT")
            (folder / f"{name}.html").write_text(html, encoding="utf-8")
            parser = PayloadParser()
            parser.feed(html)
            expected = {
                "agent-match": ["shot_map", "xg_story"],
                "agent-added-network": ["shot_map", "xg_story", "passing_network"],
                "agent-configured": ["shot_map", "xg_story", "passing_network"],
                "agent-comparison": ["shot_map", "shot_map"],
                "agent-space": ["space_partition", "play_replay"],
            }
            record["requested_recipes_created"] = sorted(
                b["insight_id"] for b in payload["blocks"]
            ) == sorted(expected[name])
            report = client.get(f"/a2a/v1/reports/{payload['report_id']}").json()
            return payload, json.loads(parser.payload), report["plan"]

        first, first_data, first_plan = execute(
            "agent-match",
            {
                "request_text": "Crea una página con exactamente dos insights del partido 900001: mapa de tiros y evolución del xG por período. Pide a data los tiros completos, con todas las páginas. Ningún otro gráfico.",
                "context": {"match_ids": [900001]},
                "analyst": {
                    "text": "Datos sintéticos de demostración. El xG disponible es ilustrativo y no calibrado."
                },
            },
        )
        if first_data:
            added, added_data, added_plan = execute(
                "agent-added-network",
                {
                    "request_text": "Añade a esta página una red de pases completados del equipo 1 durante el primer tiempo. Conserva los dos gráficos existentes y el análisis. Una red esquemática es suficiente: pide sólo get_passing_network, no pases individuales ni tracking.",
                    "report_id": first["report_id"],
                    "expected_revision": first["revision"],
                },
            )
            if added_data:
                records[-1]["preserved_block_ids"] = {
                    b["id"] for b in first_plan["blocks"]
                } <= {b["id"] for b in added_plan["blocks"]}
                styled, styled_data, styled_plan = execute(
                    "agent-configured",
                    {
                        "request_text": "Cambia el color del equipo 1 a #7352a1. En la red configura min_edge_weight=3 y span=full. Conserva todos los gráficos y el análisis; no consultes nuevos datos.",
                        "report_id": added["report_id"],
                        "expected_revision": added["revision"],
                    },
                )
                if styled_data:
                    records[-1]["configuration_applied"] = any(
                        t["team_id"] == 1 and t["color"].lower() == "#7352a1"
                        for t in styled_plan["teams"]
                    ) and any(
                        b["insight_id"] == "passing_network"
                        and b["visual"]["min_edge_weight"] == 3
                        and b["visual"]["span"] == "full"
                        for b in styled_plan["blocks"]
                    )
                    records[-1]["no_new_data"] = styled["timings_ms"]["data_http"] == 0
                    records[-1]["analysis_preserved"] = (
                        styled_plan["analyst"] == first_plan["analyst"]
                    )
            supplied = {
                "request_id": first["data_request_ids"][0],
                "status": "complete",
                "model": "beam-free",
                "evidence": first_data["evidence"],
            }
            execute(
                "agent-comparison",
                {
                    "request_text": "Crea otra página comparando los tiros de los equipos 1 y 2 del partido 900001. Usa exactamente dos shot_map, uno por equipo, en template entity_comparison. Usa la evidencia suministrada sin pedir más datos.",
                    "context": {"match_ids": [900001]},
                    "data_result": supplied,
                },
            )
        execute(
            "agent-space",
            {
                "request_text": "Crea una página de un episodio del partido 900001: Voronoi de ambos equipos en P1 tiempo 600000ms y replay de tracking de P1 desde 595000 hasta 605000ms a 1Hz. Solicita a data get_space_coverage del equipo 1 en ese instante y get_tracking_window de esa ventana; sólo esos datos. El frame 600000 de esa ventana sirve para superponer jugadores. Conserva procedencia sintética.",
                "context": {"match_ids": [900001]},
            },
        )
    result = {
        "model": "beam-free",
        "free_only": True,
        "mock_model": False,
        "cases": records,
        "pages_generated": sum(
            r["status"] in {"complete", "partial"}
            for r in records
            if r["revision"] == 1
        ),
        "all_under_one_minute": all(r["wall_seconds"] < 60 for r in records),
        "passed": len(records) == 5
        and all(r["status"] == "complete" and r["wall_seconds"] < 60 for r in records)
        and all(
            r.get(k, True)
            for r in records
            for k in (
                "preserved_block_ids",
                "configuration_applied",
                "no_new_data",
                "analysis_preserved",
                "requested_recipes_created",
            )
        ),
    }
    (folder / "verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "cases"}, ensure_ascii=True
        ),
        flush=True,
    )
    return result["passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8085")
    parser.add_argument(
        "--output-dir", type=Path, default=Path(".temp/insights/agent-qa")
    )
    raise SystemExit(0 if run(parser.parse_args()) else 1)
