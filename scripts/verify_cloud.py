"""QA remoto de API y MCP con credenciales reales leídas de un archivo privado.

No imprime claves. Comprueba las 34 operaciones HTTP y MCP, tres identidades,
rechazo de acceso anónimo/clave falsa, metadatos y resultados conocidos de Azure.
"""

import argparse
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx
import httpx2
from azure_runtime import ROOT, save_state
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from verify_api import verification_cases


async def verify(private_file):
    state = json.loads((ROOT / "deployment/cloud.json").read_text(encoding="utf-8"))
    credentials = json.loads(private_file.read_text(encoding="utf-8"))["credentials"]
    owner = next(c for c in credentials if c["id"] == "team-owner")
    report = {
        "tested_at_utc": datetime.now(UTC).isoformat(),
        "source": "Public HTTPS Azure Container Apps -> managed identity -> Azure SQL",
        "url": state["url"],
        "status": "running",
        "http_operations": [],
        "mcp_operations": [],
        "checks": [],
    }

    def check(name, passed):
        report["checks"].append({"name": name, "passed": bool(passed)})
        print(json.dumps(report["checks"][-1]), flush=True)

    async with httpx.AsyncClient(
        base_url=state["url"], timeout=90, trust_env=False
    ) as http:
        check(
            "Anonymous API access rejected",
            (await http.get("/api/matches")).status_code == 401,
        )
        check(
            "Anonymous MCP access rejected",
            (
                await http.post(
                    "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
                )
            ).status_code
            == 401,
        )
        check(
            "Forged bearer rejected",
            (
                await http.get(
                    "/api/whoami", headers={"Authorization": "Bearer " + "wrong" * 10}
                )
            ).status_code
            == 401,
        )
        for credential in credentials:
            if not credential.get("enabled", True):
                continue
            r = await http.get(
                "/api/whoami", headers={"Authorization": "Bearer " + credential["key"]}
            )
            check(
                "Identity " + credential["id"],
                r.status_code == 200
                and r.json().get("credential_id") == credential["id"]
                and r.json().get("role") == credential["role"],
            )
            query = await http.post(
                "/api/operations/get_shots",
                headers={"Authorization": "Bearer " + credential["key"]},
                json={
                    "match_id": 900001,
                    "team_id": 1,
                    "outcome": "on_target",
                    "view": "summary",
                },
            )
            check(
                "Read query by " + credential["id"],
                query.status_code == 200
                and query.json().get("data", {}).get("total") == 6,
            )

        http.headers["Authorization"] = "Bearer " + owner["key"]

        async def data(name, args):
            response = await http.post("/api/operations/" + name, json=args)
            if response.status_code != 200:
                print(
                    json.dumps(
                        {
                            "operation": name,
                            "status_code": response.status_code,
                            "error": response.json(),
                        }
                    ),
                    flush=True,
                )
            response.raise_for_status()
            return response.json()["data"]

        shots = await data("get_shots", {"match_id": 900001, "limit": 1})
        passes = await data(
            "get_passes", {"match_id": 900001, "height": "ground", "limit": 1}
        )
        first_pass = passes["items"][0]
        cases = verification_cases(
            {
                "event_shots": [{"event_id": shots["items"][0]["event_id"]}],
                "event_passes": [first_pass["pass"]],
                "event_index": {first_pass["event_id"]: first_pass},
            }
        )
        for name, args in cases.items():
            response = await http.post("/api/operations/" + name, json=args)
            passed = (
                response.status_code == 200
                and response.json().get("provenance", {}).get("is_synthetic") is True
            )
            report["http_operations"].append(
                {"name": name, "status_code": response.status_code, "passed": passed}
            )
            print(json.dumps(report["http_operations"][-1]), flush=True)
        expected = await data(
            "get_shots",
            {
                "match_id": 900001,
                "team_id": 1,
                "outcome": "on_target",
                "view": "summary",
            },
        )
        check("Known six on-target shots", expected["total"] == 6)
        invalid = await http.post(
            "/api/operations/get_shots", json={"match_id": 900001, "sql": "SELECT 1"}
        )
        check("SQL fields rejected", invalid.status_code == 422)

    agent = next(c for c in credentials if c["id"] == "agent-data")
    async with httpx2.AsyncClient(
        headers={"Authorization": "Bearer " + agent["key"]}, timeout=90, trust_env=False
    ) as transport_http:

        @asynccontextmanager
        async def transport():
            async with streamable_http_client(
                state["url"] + "/mcp", http_client=transport_http
            ) as streams:
                yield streams

        async with Client(transport(), read_timeout_seconds=90) as mcp:
            tools = (await mcp.list_tools()).tools
            check("Agent discovers 34 MCP tools", len(tools) == 34)
            for name, args in cases.items():
                result = await mcp.call_tool(name, args)
                passed = (
                    not result.is_error
                    and result.structured_content is not None
                    and result.structured_content["provenance"]["is_synthetic"] is True
                )
                report["mcp_operations"].append({"name": name, "passed": passed})
                print(json.dumps(report["mcp_operations"][-1]), flush=True)
            result = await mcp.call_tool(
                "get_shots",
                {
                    "match_id": 900001,
                    "team_id": 1,
                    "outcome": "on_target",
                    "view": "summary",
                },
            )
            check(
                "Agent MCP result equals team HTTP result",
                result.structured_content["data"] == expected,
            )
    all_checks = report["checks"] + report["http_operations"] + report["mcp_operations"]
    report["status"] = "passed" if all(c["passed"] for c in all_checks) else "failed"
    (ROOT / "docs/cloud-verification.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    if report["status"] == "passed":
        state["status"] = "deployed-and-verified"
        state["verified_at_utc"] = report["tested_at_utc"]
        save_state(state)
    print(
        json.dumps(
            {
                "status": report["status"],
                "http_operations": len(report["http_operations"]),
                "mcp_operations": len(report["mcp_operations"]),
                "checks": len(report["checks"]),
            }
        )
    )
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-file", type=Path, required=True)
    asyncio.run(verify(parser.parse_args().private_file))
