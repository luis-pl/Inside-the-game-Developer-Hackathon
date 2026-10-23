"""Verifica el recorrido cliente MCP -> API activa -> datos sintéticos de Azure.

Uso: python scripts/verify_mcp.py --transport stdio
     python scripts/verify_mcp.py --transport streamable-http

Requiere la API iniciada; HTTP requiere además el servidor MCP. No modifica
filas SQL. Escribe la evidencia local en docs/mcp-verification-<transporte>.json.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters
from verify_api import verification_cases

from inside_game.service import OPERATIONS

ROOT = Path(__file__).resolve().parents[1]


async def verify(transport, url):
    """Comprueba catálogo, 34 operaciones y resultados conocidos de la simulación."""
    # stdio inicia un proceso MCP que el cliente cierra al terminar. HTTP usa
    # el servidor ya activo. Sólo la API necesita autenticarse contra Azure.
    target = (
        url
        if transport == "streamable-http"
        else StdioServerParameters(
            command=sys.executable,
            args=["-m", "inside_game.mcp_server"],
            cwd=ROOT,
            env={k: v for k, v in os.environ.items() if k.startswith("INSIDE_GAME_")},
        )
    )
    report = {
        "tested_at_utc": datetime.now(UTC).isoformat(),
        "source": "MCP client -> HTTP API -> actual Azure SQL synthetic views",
        "transport": transport,
        "status": "running",
        "operations": [],
        "checks": [],
    }
    async with Client(target, read_timeout_seconds=45) as client:
        tools = (await client.list_tools()).tools
        assert {t.name for t in tools} == set(OPERATIONS)

        async def data(name, args):
            result = await client.call_tool(name, args)
            if result.is_error:
                raise RuntimeError(name + ": " + result.content[0].text)
            assert result.structured_content["provenance"]["is_synthetic"] is True
            return result.structured_content["data"]

        # Descubre UUID reales del conjunto actual para no fijar identificadores
        # de eventos que podrían cambiar si se regenera la data sintética.
        shots = await data("get_shots", {"match_id": 900001, "limit": 1})
        passes = await data(
            "get_passes", {"match_id": 900001, "height": "ground", "limit": 1}
        )
        shot_id, pass_item = shots["items"][0]["event_id"], passes["items"][0]
        cases = verification_cases(
            {
                "event_shots": [{"event_id": shot_id}],
                "event_passes": [pass_item["pass"]],
                "event_index": {pass_item["event_id"]: pass_item},
            }
        )
        results = {}
        for name, args in cases.items():
            start = time.monotonic()
            result = await client.call_tool(name, args)
            passed = not result.is_error and result.structured_content is not None
            report["operations"].append(
                {
                    "operation": name,
                    "passed": passed,
                    "seconds": round(time.monotonic() - start, 3),
                }
            )
            print(json.dumps(report["operations"][-1]), flush=True)
            if passed:
                payload = result.structured_content
                assert payload["operation_id"] == name
                assert payload["provenance"]["is_synthetic"] is True
                assert (
                    payload["warnings"]
                    and payload["coverage"]
                    and payload["coordinates"]
                )
                results[name] = payload["data"]

        def check(label, passed):
            report["checks"].append({"label": label, "passed": bool(passed)})

        # Estos valores corresponden a la carga sintética auditada. Además de
        # comprobar el protocolo, detectan totales duplicados o pérdida de datos.
        check("34 closed tools discovered", len(tools) == 34)
        check(
            "Known team shots on target = 6",
            results.get("get_shots", {}).get("total") == 6,
        )
        check(
            "Aerial contests = 9, no double counting",
            results.get("get_defensive_actions", {}).get("total") == 9,
        )
        check(
            "Six substitutions", results.get("get_substitutions", {}).get("total") == 6
        )
        frame = results.get("get_tracking_frame", {}).get("frames", [{}])[0]
        check("22 active players in tracking", len(frame.get("players", [])) == 22)
        coverage = (
            results.get("get_space_coverage", {})
            .get("samples", [{}])[0]
            .get("result", {})
        )
        check(
            "Voronoi area = 7140 m2", abs(coverage.get("area_sum_m2", 0) - 7140) < 1e-6
        )
        invalid = await client.call_tool(
            "get_shots", {"match_id": 900001, "sql": "SELECT 1"}
        )
        check("SQL rejected", invalid.is_error)
        unknown = await client.call_tool("execute_query", {"sql": "SELECT 1"})
        check("Unregistered tool rejected", unknown.is_error)
    report["status"] = (
        "passed"
        if all(item["passed"] for item in report["operations"] + report["checks"])
        else "failed"
    )
    path = ROOT / "docs" / ("mcp-verification-" + transport + ".json")
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "operations": len(cases),
                "checks": len(report["checks"]),
            }
        )
    )
    if report["status"] != "passed":
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--transport", choices=("stdio", "streamable-http"), default="stdio"
    )
    parser.add_argument("--url", default="http://127.0.0.1:8001/mcp")
    args = parser.parse_args()
    asyncio.run(verify(args.transport, args.url))


if __name__ == "__main__":
    main()
