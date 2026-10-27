"""QA real acotado del analista, Data, Insights, MCP y SQL; sólo Beam Free."""

import argparse
import json
import os
import time
from pathlib import Path
from uuid import uuid4

import httpx

from inside_game.agents.insights_http_client import PayloadParser
from inside_game.agents_cli import load_local_env
from inside_game.tools.mcp_client import DataMcpSettings


def run(args):
    load_local_env(Path(__file__).resolve().parents[1])
    if not (
        os.getenv("INSIDE_GAME_MODEL_PROVIDER") == "opencode-go"
        and os.getenv("INSIDE_GAME_OPENCODE_MODEL") == "beam-free"
        and os.getenv("INSIDE_GAME_OPENCODE_FREE_ONLY") == "1"
    ):
        raise ValueError("QA_REQUIRES_FREE_ONLY_BEAM_GO")
    folder = args.output_dir
    folder.mkdir(parents=True, exist_ok=True)
    key = DataMcpSettings.from_env().key
    cases = []
    with httpx.Client(
        base_url=args.base_url,
        headers={"Authorization": "Bearer " + key},
        timeout=65,
        trust_env=False,
        follow_redirects=False,
    ) as client:

        def execute(name, request):
            request = {"request_id": str(uuid4()), **request}
            (folder / f"{name}.request.json").write_text(
                json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            started = time.perf_counter()
            response = client.post("/a2a/v1/analysis-reports", json=request)
            result = response.json()
            wall = round(time.perf_counter() - started, 3)
            (folder / f"{name}.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            analysis = result.get("analysis", {})
            item = {
                "case": name,
                "http": response.status_code,
                "wall_seconds": wall,
                "status": analysis.get("status"),
                "issues": analysis.get("issues", []),
                "tool_trace": analysis.get("tool_trace", []),
                "model_turns": analysis.get("model_turns"),
                "facts": len(analysis.get("facts", [])),
                "has_report": bool(result.get("report")),
            }
            cases.append(item)
            print(json.dumps(item), flush=True)
            if analysis.get("text"):
                (folder / f"{name}.md").write_text(analysis["text"], encoding="utf-8")
            if result.get("report"):
                page = client.get(result["report"]["artifact_url"])
                page.raise_for_status()
                assert key not in page.text
                (folder / f"{name}.html").write_text(page.text, encoding="utf-8")
                parser = PayloadParser()
                parser.feed(page.text)
                payload = json.loads("".join(parser.parts))
                assert payload["analyst"]["text"] == analysis["text"]
                assert all(b["state"] == "ready" for b in payload["blocks"])
                item["analysis_preserved"] = True
                item["blocks"] = [b["insight_id"] for b in payload["blocks"]]
                return payload
            return None

        supplied = {}
        data_wall = 0
        if args.data_first:
            request = {
                "request_id": str(uuid4()),
                "request_text": "Recupera get_team_shape view geometry y get_proximity_connectivity epsilon_m=15 del equipo 1, match 900001, P1 time_ms=600000. Recupera get_tracking_frame del mismo instante con todos los jugadores. Sólo esas tres consultas.",
                "context": {"match_ids": [900001], "team_ids": [1]},
            }
            started = time.perf_counter()
            response = client.post("/a2a/v1/data", json=request)
            response.raise_for_status()
            data_wall = round(time.perf_counter() - started, 3)
            data = response.json()
            (folder / "data.request.json").write_text(
                json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (folder / "data.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            assert data["status"] == "complete", data.get("issues")
            supplied = {"data_result": data}
            print(
                json.dumps(
                    {
                        "stage": "data-first",
                        "seconds": data_wall,
                        "status": data["status"],
                    }
                ),
                flush=True,
            )
        first = execute(
            "topology-analysis",
            {
                **supplied,
                "request_text": "Analiza la organización espacial del equipo 1 del partido 900001 en P1, instante 600000 ms. Pide a Data exactamente get_team_shape view geometry, get_proximity_connectivity epsilon_m=15 y get_tracking_frame de ese instante; agrupa la recuperación. Pide a Insights exactamente dos piezas: team_shape y proximity_network, con el frame superpuesto. Redacta tres apartados breves: forma, conectividad y límites. Usa mediciones concretas con placeholders de hechos y una interpretación prudente; no generalices al partido ni afirmes impenetrabilidad.",
                "context": {"match_ids": [900001], "team_ids": [1]},
            },
        )
        if first:
            execute(
                "reused-topology-analysis",
                {
                    "request_text": "Con la evidencia suministrada de este episodio, redacta una explicación para alguien sin conocimientos técnicos. Usa exactamente team_shape y proximity_network para acompañarla. Explica qué permiten observar la anchura, la longitud y las componentes a la distancia registrada, y qué no prueban sobre la defensa. Tres apartados cortos. No consultes nuevos datos.",
                    "context": {"match_ids": [900001], "team_ids": [1]},
                    "data_result": {
                        "request_id": str(uuid4()),
                        "status": "complete",
                        "model": "original-evidence-reuse",
                        "evidence": first["evidence"],
                    },
                },
            )
        if args.advanced_request:
            advanced = json.loads(args.advanced_request.read_text(encoding="utf-8"))
            advanced.pop("request_id", None)
            execute("advanced-topology", advanced)
            record = {**cases[-1], "data_reused": True}
            (folder / "advanced-verification.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        result = {
            "provider": "opencode-go",
            "model": "beam-free",
            "free_only": True,
            "mock_model": False,
            "cases": cases,
            "data_first_seconds": data_wall,
            "first_page_end_to_end_seconds": round(
                data_wall + cases[0]["wall_seconds"], 3
            ),
            "passed": len(cases) == (3 if args.advanced_request else 2)
            and all(
                c["status"] == "complete"
                and c["has_report"]
                and c["analysis_preserved"]
                for c in cases
            ),
        }
        (folder / "verification.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return result["passed"]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default="http://127.0.0.1:8088")
    p.add_argument("--output-dir", type=Path, default=Path(".temp/insights/analyst-qa"))
    p.add_argument(
        "--advanced-request",
        type=Path,
        help="Repite el caso avanzado exportado con su evidencia original; no recupera esos datos de SQL otra vez.",
    )
    p.add_argument(
        "--data-first",
        action="store_true",
        help="Data obtiene evidencia antes del analista, igual que en una orquestación con intérprete.",
    )
    raise SystemExit(0 if run(p.parse_args()) else 1)
