"""Prueba el ejecutor con planes controlados y MCP/SQL reales, SIN usar un LLM.

Permite verificar transporte, paginación y evidencia aun cuando Azure no tenga
cuota de inferencia. No evalúa comprensión del texto ni sustituye la prueba Luna.
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from azure_runtime import ROOT

from inside_game.agents.data_agent import DataAgent
from inside_game.providers.models import ModelTurn
from inside_game.tools.mcp_client import DataMcpSettings, connect_data_mcp


class ControlledPlan:
    name = "controlled-plan-NOT-an-LLM"

    def __init__(self, calls):
        self.calls = list(calls)
        self.index = 0

    async def respond(self, instructions, messages, tools):
        self.index += 1
        if self.calls:
            name, args = self.calls.pop(0)
        else:
            ids = []
            for message in messages:
                if message.get("type") == "function_call_output":
                    result = json.loads(message["output"])
                    ids.extend(
                        p["evidence_id"]
                        for p in result.get("pages", [])
                        if "evidence_id" in p
                    )
            name, args = (
                "finish_data_request",
                {
                    "status": "complete",
                    "evidence_ids": ids,
                    "clarification": None,
                    "notes": [],
                },
            )
        return ModelTurn(
            [
                {
                    "type": "function_call",
                    "call_id": f"controlled-{self.index}",
                    "name": name,
                    "arguments": json.dumps(args),
                }
            ]
        )


async def verify(private_file):
    private = json.loads(private_file.read_text(encoding="utf-8"))
    if private.get("credential_id") != "agent-data":
        raise ValueError("Use only the individual agent-data handoff file")
    cloud = json.loads((ROOT / "deployment/cloud.json").read_text(encoding="utf-8"))
    cases = [
        (
            "on_target_shots",
            "Obtén tiros a puerta, tiempo y ubicación",
            [
                (
                    "get_shots",
                    {"match_id": 900001, "team_id": 1, "outcome": "on_target"},
                ),
            ],
        ),
        (
            "three_players_positioning",
            "Mapas y movimiento de tres jugadores en el segundo tiempo",
            [
                (
                    operation,
                    {
                        "match_id": 900001,
                        "player_id": pid,
                        "scope": {"kind": "period", "period": 2},
                    },
                )
                for pid in (106, 108, 110)
                for operation in ("get_heatmap", "get_movement_summary")
            ],
        ),
        (
            "multiple_matches",
            "Pases del jugador entre partidos",
            [
                (
                    "get_player_summary",
                    {
                        "match_ids": [900001, 900003],
                        "player_id": 110,
                        "profile_id": "passing",
                    },
                ),
            ],
        ),
        (
            "all_passes_paginated",
            "Todos los pases del partido",
            [
                ("get_passes", {"match_id": 900001, "limit": 100}),
            ],
        ),
        (
            "defensive_geometry",
            "Forma, conectividad y área Voronoi",
            [
                (
                    operation,
                    {"match_id": 900001, "team_id": 2, "period": 1, "time_ms": 600000},
                )
                for operation in (
                    "get_team_shape",
                    "get_proximity_connectivity",
                    "get_space_coverage",
                )
            ],
        ),
        (
            "pressure_sequence",
            "Secuencias de presión a recuperación",
            [
                (
                    "get_sequences",
                    {
                        "match_id": 900001,
                        "team_id": 1,
                        "pattern_id": "pressure_to_recovery",
                    },
                ),
            ],
        ),
    ]
    report = {
        "tested_at_utc": datetime.now(UTC).isoformat(),
        "llm_used": False,
        "source": "Controlled plan -> DataAgent -> public authenticated MCP -> Azure SQL",
        "natural_language_evaluated": False,
        "status": "running",
        "cases": [],
    }
    destination = ROOT / "docs/data-agent-transport-verification.json"
    async with connect_data_mcp(
        DataMcpSettings(cloud["url"] + "/mcp", private["key"])
    ) as mcp:
        for name, text, calls in cases:
            result = await DataAgent(ControlledPlan(calls)).run(text, mcp)
            checks = {
                "complete": result.status == "complete",
                "all_queries": {e.operation for e in result.evidence}
                == {c[0] for c in calls},
                "synthetic": all(
                    e.response.provenance.get("is_synthetic") is True
                    for e in result.evidence
                ),
                "original_data_preserved": True,
            }
            for evidence in result.evidence:
                direct = await mcp.call_tool(evidence.operation, evidence.arguments)
                if (
                    direct.is_error
                    or direct.structured_content["data"] != evidence.response.data
                ):
                    checks["original_data_preserved"] = False
                    break
            if name == "on_target_shots":
                checks["known_six_shots"] = (
                    bool(result.evidence)
                    and result.evidence[0].response.data.get("total") == 6
                )
            if name == "three_players_positioning":
                checks["six_player_outputs"] = len(result.evidence) == 6
            if name == "all_passes_paginated":
                checks["multiple_pages"] = len(result.evidence) > 1
                checks["last_page"] = bool(result.evidence) and not result.evidence[
                    -1
                ].response.pagination.get("next_cursor")
            item = {
                "name": name,
                "passed": all(checks.values()),
                "checks": checks,
                "status": result.status,
                "tool_calls": result.tool_calls,
                "evidence_pages": len(result.evidence),
                "issues": [i.model_dump() for i in result.issues],
            }
            report["cases"].append(item)
            destination.write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )
            print(json.dumps(item), flush=True)
    report["status"] = (
        "passed" if all(c["passed"] for c in report["cases"]) else "failed"
    )
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report["status"] == "passed"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-file", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if asyncio.run(verify(args.private_file)) else 1)
