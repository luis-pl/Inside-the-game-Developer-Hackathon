"""Evalúa el planificador con el modelo configurado y datos reales de la API.

Usa `create_model()` (la configuración Go / Beam Free con FREE_ONLY=1 vive en el
entorno, nunca aquí) y el cliente de datos in-process. Compara cada intención con
la esperada en tests/fixtures/insights_planner_cases.json. Una ejecución acotada
no equivale a QA del corpus completo.
"""

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

import httpx

from inside_game.agents.insights_agent.planner import Planner
from inside_game.dashboard.config import DashboardConfig
from inside_game.local_env import load_local_env
from inside_game.providers.models import create_model
from inside_game.tools.evidence_client import (
    EvidenceClient,
    HttpTransport,
)

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "tests/fixtures/insights_planner_cases.json"


def score(case, result):
    expect = case["expect"]
    checks = {"status": result.status == expect["status"]}
    intent = result.intent.model_dump() if result.intent else {}
    for field, value in expect.get("intent", {}).items():
        checks[field] = intent.get(field) == value
    for key in expect.get("insight_ids_include", []):
        checks[f"insight:{key}"] = key in intent.get("insight_ids", [])
    return all(checks.values()), checks


async def run(cases, output):
    config = DashboardConfig.load(ROOT)
    report = {"cases": []}
    async with (
        httpx.AsyncClient(
            base_url=config.api_url,
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=120,
            follow_redirects=False,
            trust_env=False,
        ) as http,
        create_model() as model,
    ):
        data = EvidenceClient(HttpTransport(http))
        planner = Planner(model, data)
        report |= {"model": model.name, "prompt_sha256": None}
        for case in cases:
            started = time.perf_counter()
            result = await planner.plan(
                {
                    "question": case["question"],
                    "previous_intent": case.get("previous_intent"),
                }
            )
            passed, checks = score(case, result)
            row = {
                "id": case["id"],
                "question": case["question"],
                "passed": passed,
                "failed_checks": [k for k, ok in checks.items() if not ok],
                "status": result.status,
                "intent": result.intent.model_dump(exclude_defaults=True)
                if result.intent
                else None,
                "message": result.message,
                "options": result.options,
                "issues": result.issues,
                "model_turns": result.model_turns,
                "tool_calls": result.tool_calls,
                "total_tokens": result.total_tokens,
                "seconds": round(time.perf_counter() - started, 1),
            }
            report["prompt_sha256"] = result.prompt_sha256
            report["cases"].append(row)
            print(
                f"{'OK ' if passed else 'FAIL'} {case['id']:24} {result.status:13} "
                f"turns={result.model_turns} {row['seconds']}s {row['failed_checks'] or ''} "
                f"{row['intent'] or row['message'] or row['issues']}",
                flush=True,
            )
            if any(i.startswith("MODEL_") for i in result.issues):
                # Error del modelo o su configuración (credenciales, despliegue,
                # cuota, gratuidad): no se siguen gastando tokens en más casos.
                report["stopped"] = result.issues
                break
    rows = report["cases"]
    report["summary"] = {
        "passed": sum(r["passed"] for r in rows),
        "total": len(rows),
        "median_seconds": sorted(r["seconds"] for r in rows)[len(rows) // 2]
        if rows
        else None,
        "total_tokens": sum(r["total_tokens"] for r in rows),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report["summary"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", help="Sólo estos IDs")
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".temp/insights/planner-eval.json"
    )
    args = parser.parse_args()
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    if args.case:
        cases = [c for c in cases if c["id"] in args.case]
    # Endpoint y clave del modelo viven en .env.local; el proveedor y el despliegue
    # se eligen explícitamente en el entorno del comando (nunca por defecto).
    load_local_env(ROOT)
    load_local_env(ROOT, prefix="AZURE_")
    if not os.getenv("INSIDE_GAME_MODEL_PROVIDER"):
        parser.exit(
            1,
            "Elige el modelo con INSIDE_GAME_MODEL_PROVIDER (docs/insights-agent.md).\n",
        )
    asyncio.run(run(cases, args.output))


if __name__ == "__main__":
    main()
