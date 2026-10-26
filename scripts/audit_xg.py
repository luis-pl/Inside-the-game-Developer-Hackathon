"""Audita xG leyendo la API; no cambia SQL ni calcula xG para fuentes reales."""

import asyncio
import json
import math
from collections import defaultdict
from pathlib import Path

import httpx

from inside_game.agents_cli import load_local_env
from inside_game.tools.evidence_client import HttpTransport
from inside_game.tools.mcp_client import DataMcpSettings


def inspect_shots(payload):
    rows = payload["data"]["items"]
    values, teams, errors = [], defaultdict(list), []
    for row in rows:
        value = row["shot"].get("statsbomb_xg")
        if value is None:
            continue
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not 0 <= value <= 1
        ):
            errors.append({"event_id": row["event_id"], "error": "INVALID_PROBABILITY"})
            continue
        values.append(value)
        teams[row["team_id"]].append(value)
        if payload["provenance"]["is_synthetic"]:
            x, y = row["attacking_x_m"], row["attacking_y_m"]
            distance = math.hypot(105 - x, 34 - y)
            angle = abs(math.atan2(37.66 - y, 105 - x) - math.atan2(30.34 - y, 105 - x))
            expected = min(
                0.65,
                max(
                    0.01,
                    0.36 * math.exp(-distance / 24) * min(1.5, max(0.25, angle / 0.5)),
                ),
            )
            if not math.isclose(value, expected, abs_tol=1e-10):
                errors.append(
                    {
                        "event_id": row["event_id"],
                        "error": "GENERATOR_FORMULA_MISMATCH",
                        "stored": value,
                        "recomputed": expected,
                    }
                )
    total = math.fsum(values) if len(values) == len(rows) else None
    api_total = payload["data"]["summary"].get("xg")
    if total is not None and not math.isclose(total, api_total, abs_tol=1e-10):
        errors.append({"error": "API_SUM_MISMATCH"})
    if not payload["provenance"]["is_synthetic"] and (values or api_total is not None):
        errors.append({"error": "UNEXPECTED_REAL_SOURCE_XG"})
    return {
        "shots": len(rows),
        "shots_with_xg": len(values),
        "xg": total,
        "api_xg": api_total,
        "team_xg": {str(k): math.fsum(v) for k, v in teams.items()},
        "goals": payload["data"]["summary"].get("goals"),
        "is_synthetic": payload["provenance"]["is_synthetic"],
        "errors": errors,
        "passed": not errors,
    }


async def run(folder):
    load_local_env(Path(__file__).resolve().parents[1])
    settings = DataMcpSettings.from_env()
    folder.mkdir(parents=True, exist_ok=True)
    records = []
    async with httpx.AsyncClient(
        base_url=settings.url.removesuffix("/mcp"),
        headers={"Authorization": "Bearer " + settings.key},
        timeout=90,
        trust_env=False,
    ) as http:
        transport = HttpTransport(http)
        for match_id in [
            *range(900001, 900011),
            900011,
            900012,
            *range(900101, 900109),
        ]:
            payload, error = await transport.call(
                "get_shots", {"match_id": match_id, "view": "events", "limit": 200}
            )
            if error:
                record = {"match_id": match_id, "passed": False, "error": error}
            else:
                assert not payload["pagination"].get("next_cursor"), (
                    "AUDIT_REQUIRES_ALL_SHOTS"
                )
                (folder / f"shots-{match_id}.json").write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                record = {"match_id": match_id, **inspect_shots(payload)}
            records.append(record)
            print(json.dumps(record), flush=True)
    result = {
        "read_only": True,
        "matches": records,
        "passed": all(r["passed"] for r in records),
        "synthetic_xg_model": "toy-distance-angle-v2; not calibrated",
    }
    (folder / "xg-audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=Path(".temp/insights/xg-review")
    )
    raise SystemExit(
        0 if asyncio.run(run(parser.parse_args().output_dir))["passed"] else 1
    )
