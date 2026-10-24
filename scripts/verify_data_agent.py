"""Evalúa texto -> modelo Azure real -> MCP real con el corpus del repositorio.

Lee sólo la credencial individual agent-data fuera de Git. El informe conserva
operaciones, argumentos y verificaciones, nunca claves ni respuestas de Azure
OpenAI. No usa un modelo simulado ni modifica registros SQL.
"""

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from azure_runtime import ROOT

from inside_game.agents.data_agent import DataAgent
from inside_game.providers.models import create_model, model_settings_from_env
from inside_game.tools.mcp_client import DataMcpSettings, connect_data_mcp


async def verify(args):
    credential = json.loads(args.private_file.read_text(encoding="utf-8"))
    if credential.get("credential_id") != "agent-data":
        raise ValueError("Use only the individual agent-data handoff file")
    state = json.loads((ROOT / "deployment/cloud.json").read_text(encoding="utf-8"))
    model_file = ROOT / "deployment/agent-model.json"
    provider = os.getenv("INSIDE_GAME_MODEL_PROVIDER", "azure")
    if model_file.exists() and provider == "azure":
        model_state = json.loads(model_file.read_text(encoding="utf-8"))
        unselected = model_state.get("selected_for_agent") is False
        if (not model_state.get("deployment_created") or unselected) and not os.getenv(
            "AZURE_OPENAI_ENDPOINT"
        ):
            report = {
                "tested_at_utc": datetime.now(UTC).isoformat(),
                "status": "blocked",
                "reason": "MODEL_NOT_SELECTED"
                if unselected
                else model_state.get("deployment_error"),
                "model": model_state["model"],
                "llm_used": False,
                "natural_language_evaluated": False,
                "cases": [],
                "detail": "No approved model selected or no deployment available. Unit and controlled transport tests are separate.",
            }
            args.report.write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )
            print(json.dumps(report), flush=True)
            return False
        os.environ.setdefault("AZURE_OPENAI_ENDPOINT", model_state["endpoint"])
        os.environ.setdefault("AZURE_OPENAI_DEPLOYMENT", model_state["deployment"])
        os.environ.setdefault(
            "INSIDE_GAME_MODEL_API", model_state.get("api", "responses")
        )
    mcp_settings = DataMcpSettings(state["url"] + "/mcp", credential["key"])
    cases = json.loads(
        (ROOT / "tests/fixtures/data_agent_cases.json").read_text(encoding="utf-8")
    )
    if args.case:
        cases = [case for case in cases if case["id"] in args.case]
        if not cases:
            raise ValueError("Unknown case")
    model_settings = model_settings_from_env()
    report = {
        "tested_at_utc": datetime.now(UTC).isoformat(),
        "source": "Configured model -> authenticated MCP -> Azure SQL (synthetic)",
        "provider": provider,
        "model": model_settings.deployment,
        "model_api": model_settings.api,
        "llm_used": True,
        "natural_language_evaluated": True,
        "status": "running",
        "cases": [],
    }
    async with (
        create_model(model_settings) as model,
        connect_data_mcp(mcp_settings) as mcp,
    ):
        agent = DataAgent(model)
        for case in cases:
            result = await agent.run(case["request"], mcp)
            evidence = result.evidence
            operations = {e.operation for e in evidence}
            checks = {
                "expected_status": result.status in case["expected_status"],
                "required_operations": set(case["required_operations"]) <= operations,
                "synthetic_provenance": all(
                    e.response.provenance.get("is_synthetic") is True for e in evidence
                ),
                "required_arguments": all(
                    any(
                        e.operation == check["operation"]
                        and all(
                            e.arguments.get(k) == v for k, v in check["values"].items()
                        )
                        for e in evidence
                    )
                    for check in case.get("required_arguments", [])
                ),
                "required_players": all(
                    any(e.arguments.get("player_id") == pid for e in evidence)
                    for pid in case.get("required_players", [])
                ),
                "player_operation_matrix": all(
                    any(
                        e.operation == operation and e.arguments.get("player_id") == pid
                        for e in evidence
                    )
                    for pid in case.get("required_players", [])
                    for operation in case["required_operations"]
                ),
                "minimum_pages": len(evidence) >= case.get("minimum_pages", 0),
                "forbidden_calls": not case.get("forbidden_calls")
                or result.tool_calls == 0,
                "safe_rejection": not case.get("forbidden_calls")
                or result.status == "unsupported"
                or (
                    result.status == "error"
                    and bool(result.issues)
                    and all(
                        i.code in {"MODEL_REQUEST_REJECTED", "MODEL_CONTENT_FILTERED"}
                        for i in result.issues
                    )
                ),
                "clarification": result.status != "needs_clarification"
                or bool(result.clarification),
            }
            # Cotejo directo: comprueba que los datos entregados mantienen los
            # valores reales del MCP, incluso si el LLM los vio como preview.
            checks["original_data_preserved"] = True
            for e in evidence:
                original = await mcp.call_tool(e.operation, e.arguments)
                if (
                    original.is_error
                    or original.structured_content["data"] != e.response.data
                ):
                    checks["original_data_preserved"] = False
                    break
            item = {
                "id": case["id"],
                "passed": all(checks.values()),
                "status": result.status,
                "checks": checks,
                "tool_calls": result.tool_calls,
                "model_turns": result.model_turns,
                "total_tokens": result.total_tokens,
                "issues": [i.model_dump() for i in result.issues],
                "queries": [
                    {
                        "operation": e.operation,
                        "arguments": e.arguments,
                        "method_id": e.response.method_id,
                    }
                    for e in evidence
                ],
            }
            report["cases"].append(item)
            args.report.write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )
            print(
                json.dumps({k: item[k] for k in ("id", "passed", "status", "issues")}),
                flush=True,
            )
    report["status"] = (
        "passed" if all(c["passed"] for c in report["cases"]) else "failed"
    )
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report["status"] == "passed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-file", type=Path, required=True)
    parser.add_argument("--case", action="append")
    parser.add_argument(
        "--report", type=Path, default=ROOT / "docs/data-agent-verification.json"
    )
    args = parser.parse_args()
    raise SystemExit(0 if asyncio.run(verify(args)) else 1)


if __name__ == "__main__":
    main()
