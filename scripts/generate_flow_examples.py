"""Cinco páginas reales del flujo Data -> analista -> Insights, con Beam Free."""

import argparse
import json
import os
import time
from pathlib import Path
from uuid import uuid4

import httpx

from inside_game.agents.analyst_contracts import AnalysisReportResult
from inside_game.agents.insights_http_client import PayloadParser
from inside_game.agents_cli import load_local_env
from inside_game.tools.mcp_client import DataMcpSettings

CASES = [
    {
        "id": "01-ocasiones-y-xg",
        "title": "Ocasiones y xG",
        "context": {"match_ids": [900001]},
        "data": "Partido 900001: recupera get_match_context y get_shots view events de todo el partido, ambos equipos, con todas las páginas. Sólo esas operaciones.",
        "question": "Explica cómo se repartieron los tiros y el xG entre los dos equipos del partido 900001. Pide exactamente shot_map y xg_story con los datos suministrados. Redacta tres apartados breves con observaciones y una interpretación prudente. El xG es sintético e ilustrativo. No consultes nuevos datos ni atribuyas causalidad al marcador.",
        "recipes": ["shot_map", "xg_story"],
    },
    {
        "id": "02-circulacion-y-flujo",
        "title": "Circulación y flujo de pases",
        "context": {
            "match_ids": [900001],
            "team_ids": [1],
            "scope": {"kind": "period", "period": 1},
        },
        "data": "Partido 900001, equipo 1, primer tiempo: recupera get_passing_network y get_team_summary profile_id passing, ambos con scope kind period period 1. Sólo esas dos operaciones; no tracking ni pases individuales.",
        "question": "Analiza la circulación del equipo 1 durante el primer tiempo del partido 900001. Crea exactamente passing_network y hodge_flow con los datos suministrados. Explica relaciones de pase y componentes del flujo con sus límites. No confundas circulación matemática con dominio, eficacia o posesión. Tres apartados breves; no recuperes nuevos datos.",
        "recipes": ["passing_network", "hodge_flow"],
    },
    {
        "id": "03-acciones-y-progresion",
        "title": "Acciones defensivas y progresión",
        "context": {
            "match_ids": [900001],
            "team_ids": [1],
            "scope": {"kind": "window", "period": 1, "start_ms": 0, "end_ms": 900000},
        },
        "data": "Partido 900001, equipo 1, ventana P1 [0,900000) ms: recupera get_defensive_actions kind all view events y get_ball_actions kind all view events. Todas las páginas, limit 200. Sólo esas dos operaciones.",
        "question": "Describe las acciones defensivas y las acciones con balón del equipo 1 en los primeros quince minutos del partido 900001. Crea exactamente defensive_actions y ball_progression. Distingue presiones, recuperaciones, quites y acciones con balón según lo que esté anotado. No infieras presión alta ni eficacia global desde recuentos. Tres apartados breves y límites del alcance; no consultes otros datos.",
        "recipes": ["defensive_actions", "ball_progression"],
    },
    {
        "id": "04-estructura-real",
        "title": "Estructura espacial de un partido real",
        "context": {"match_ids": [900011]},
        "data": "Partido real anonimizado 900011: usa get_match_context para identificar el equipo local. Recupera get_team_shape view geometry y get_proximity_connectivity epsilon_m 15 para ese equipo, P1 time_ms 600000, y get_tracking_frame del instante con todos los jugadores. Sólo esas cuatro operaciones.",
        "question": "Analiza la forma y conectividad del equipo local del partido real anonimizado 900011, primer tiempo, instante 600000 ms. Crea exactamente team_shape y proximity_network con el frame suministrado. Distingue población, instante y cobertura. No extrapoles al partido ni inventes roles, presión, xG o fecha original. Tres apartados claros para una persona sin conocimientos técnicos. Reutiliza la evidencia.",
        "recipes": ["team_shape", "proximity_network"],
    },
    {
        "id": "05-espacio-y-episodio",
        "title": "Espacio y reproducción de un episodio",
        "context": {"match_ids": [900002], "team_ids": [3]},
        "data": "Partido sintético 900002, equipo 3, P2 time_ms 900000: get_team_shape view geometry y get_space_coverage del instante. Añade get_tracking_window de P2 [895000,905000) ms a 1 Hz con todos los jugadores. Sólo esas tres operaciones; la ventana contiene el frame 900000.",
        "question": "Explica un episodio del segundo tiempo del partido 900002: forma del equipo 3, reparto geométrico del espacio y posiciones alrededor del instante 900000 ms. Pide exactamente team_shape, space_partition y play_replay, usando la ventana suministrada. La muestra abarca diez segundos. Voronoi es cercanía geométrica, no probabilidad de control. Tres apartados breves; no infieras intención, presión ni eficacia y no consultes más datos.",
        "recipes": ["team_shape", "space_partition", "play_replay"],
    },
]


def save(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def run(args):
    load_local_env(Path(__file__).resolve().parents[1])
    if not (
        os.getenv("INSIDE_GAME_MODEL_PROVIDER") == "opencode-go"
        and os.getenv("INSIDE_GAME_OPENCODE_MODEL") == "beam-free"
        and os.getenv("INSIDE_GAME_OPENCODE_FREE_ONLY") == "1"
    ):
        raise ValueError("REQUIRES_FREE_ONLY_BEAM_GO")
    folder = args.output_dir
    folder.mkdir(parents=True, exist_ok=True)
    key = DataMcpSettings.from_env().key
    records = (
        json.loads((folder / "verification.json").read_text(encoding="utf-8"))
        if args.resume and (folder / "verification.json").is_file()
        else []
    )
    with httpx.Client(
        base_url=args.base_url,
        headers={"Authorization": "Bearer " + key},
        timeout=70,
        trust_env=False,
        follow_redirects=False,
    ) as client:
        for case in CASES:
            previous = next((r for r in records if r["id"] == case["id"]), None)
            if (
                previous
                and previous.get("page")
                and previous.get("status") == "complete"
            ):
                continue
            prior_seconds = 0
            if previous:
                prior_seconds = previous.get("end_to_end_seconds") or (
                    previous["data_seconds"]
                    + sum(a["seconds"] for a in previous["attempts"])
                )
                # Un reintento conserva el fallo y sus archivos para poder auditarlo.
                history = folder / "prior-runs" / case["id"]
                history.mkdir(parents=True, exist_ok=True)
                revision = 1 + len(list(history.glob("run-*.json")))
                save(history / f"run-{revision}.json", previous)
                for path in folder.glob(case["id"] + ".*"):
                    if path.is_file():
                        (history / f"{revision}-{path.name}").write_bytes(
                            path.read_bytes()
                        )
                records.remove(previous)
            started = time.perf_counter()
            data_request = {
                "request_id": str(uuid4()),
                "request_text": case["data"],
                "context": case["context"],
            }
            save(folder / f"{case['id']}.data-request.json", data_request)
            response = client.post(
                "/a2a/v1/data",
                json=data_request,
                headers={"X-Agent-Deadline-Ms": "45000"},
            )
            response.raise_for_status()
            data = response.json()
            data_seconds = round(time.perf_counter() - started, 3)
            save(folder / f"{case['id']}.data.json", data)
            record = {
                "id": case["id"],
                "title": case["title"],
                "data_status": data["status"],
                "data_seconds": data_seconds,
                "prior_seconds": prior_seconds,
                "attempts": [],
            }
            records.append(record)
            print(
                json.dumps(
                    {
                        "stage": "data",
                        **{k: v for k, v in record.items() if k != "attempts"},
                    }
                ),
                flush=True,
            )
            if not data["evidence"]:
                record["status"] = "data_error"
                save(folder / "verification.json", records)
                continue
            for attempt in (1, 2):
                request = {
                    "request_id": str(uuid4()),
                    "request_text": case["question"],
                    "context": case["context"],
                    "data_result": data,
                }
                save(folder / f"{case['id']}.request-{attempt}.json", request)
                before = time.perf_counter()
                response = client.post("/a2a/v1/analysis-reports", json=request)
                result = response.json()
                seconds = round(time.perf_counter() - before, 3)
                save(folder / f"{case['id']}.attempt-{attempt}.json", result)
                entry = {
                    "attempt": attempt,
                    "http": response.status_code,
                    "seconds": seconds,
                    "status": result.get("analysis", {}).get("status"),
                    "issues": result.get("analysis", {}).get("issues", []),
                }
                record["attempts"].append(entry)
                print(
                    json.dumps({"stage": "analysis", "id": case["id"], **entry}),
                    flush=True,
                )
                if not result.get("report"):
                    continue
                AnalysisReportResult.model_validate(result)
                html = client.get(result["report"]["artifact_url"])
                html.raise_for_status()
                assert key not in html.text
                parser = PayloadParser()
                parser.feed(html.text)
                payload = json.loads("".join(parser.parts))
                assert payload["analyst"]["text"] == result["analysis"]["text"]
                recipes = sorted(b["insight_id"] for b in payload["blocks"])
                assert recipes == sorted(case["recipes"]), (case["id"], recipes)
                assert all(b["state"] == "ready" for b in payload["blocks"])
                (folder / f"{case['id']}.html").write_text(html.text, encoding="utf-8")
                (folder / f"{case['id']}.md").write_text(
                    result["analysis"]["text"], encoding="utf-8"
                )
                save(folder / f"{case['id']}.json", result)
                record.update(
                    status=result["analysis"]["status"],
                    analysis_seconds=seconds,
                    end_to_end_seconds=round(
                        prior_seconds + time.perf_counter() - started, 3
                    ),
                    recipes=recipes,
                    page=case["id"] + ".html",
                    facts=len(result["analysis"]["facts"]),
                    request_text=case["question"],
                )
                break
            save(folder / "verification.json", records)
    return len(records) == 5 and all(
        r.get("page") and r.get("status") == "complete" for r in records
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default="http://127.0.0.1:8089")
    p.add_argument(
        "--resume",
        action="store_true",
        help="Conserva páginas completas y repite sólo los fallos",
    )
    p.add_argument(
        "--output-dir", type=Path, default=Path(".temp/insights/five-flow-examples")
    )
    raise SystemExit(0 if run(p.parse_args()) else 1)
