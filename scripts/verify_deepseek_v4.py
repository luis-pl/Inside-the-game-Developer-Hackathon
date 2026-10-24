"""Prueba diagnóstica acotada: DeepSeek real -> MCP real -> SQL sintético.

Expone sólo describe_dataset y get_shots para medir un catálogo pequeño. No
equivale a aprobar las 34 herramientas; su evaluación completa se conserva en
docs/deepseek-v4-verification.json. No cambia la configuración ni selecciona modelo.
"""

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

from azure_runtime import ROOT

from inside_game.agents.data_agent import DataAgent
from inside_game.providers.models import AzureChatModel, AzureModelSettings
from inside_game.tools.mcp_client import DataMcpSettings, connect_data_mcp


class DiagnosticCatalog:
    """Restringe el catálogo de la prueba; conserva esquemas y transporte reales."""

    allowed = frozenset({"describe_dataset", "get_shots"})

    def __init__(self, client):
        self.client = client

    async def list_tools(self):
        result = await self.client.list_tools()
        return SimpleNamespace(
            tools=[t for t in result.tools if t.name in self.allowed]
        )

    async def call_tool(self, name, arguments):
        if name not in self.allowed:
            raise ValueError("Tool outside diagnostic catalog")
        return await self.client.call_tool(name, arguments)


async def main():
    settings = AzureModelSettings.from_env()
    if settings.deployment != "deepseek-v4-flash":
        raise ValueError("This diagnostic is only for deepseek-v4-flash")
    async with (
        AzureChatModel(settings) as model,
        connect_data_mcp(DataMcpSettings.from_env()) as mcp,
    ):
        request = (
            "Obtén todos los tiros a puerta del equipo 1 en el partido 900001, "
            "con sus tiempos y coordenadas. Los identificadores están confirmados."
        )
        result = await DataAgent(model).run(request, DiagnosticCatalog(mcp))
        preserved = True
        for evidence in result.evidence:
            original = await mcp.call_tool(evidence.operation, evidence.arguments)
            preserved &= (
                not original.is_error
                and original.structured_content["data"] == evidence.response.data
            )
        valid_shots = any(
            e.operation == "get_shots"
            and e.arguments.get("match_id") == 900001
            and e.arguments.get("team_id") == 1
            and e.arguments.get("outcome") == "on_target"
            for e in result.evidence
        )
        report = {
            "tested_at_utc": datetime.now(UTC).isoformat(),
            "model": settings.deployment,
            "llm_used": True,
            "real_authenticated_mcp_and_sql": True,
            "catalog_scope": sorted(DiagnosticCatalog.allowed),
            "full_catalog_evaluated_here": False,
            "status": result.status,
            "passed": result.status == "complete" and valid_shots and preserved,
            "correct_shot_parameters": valid_shots,
            "original_data_preserved": preserved,
            "synthetic_provenance": all(
                e.response.provenance.get("is_synthetic") is True
                for e in result.evidence
            ),
            "model_turns": result.model_turns,
            "total_tokens": result.total_tokens,
            "tool_calls": result.tool_calls,
            "issues": [i.model_dump() for i in result.issues],
            "queries": [
                {"operation": e.operation, "arguments": e.arguments}
                for e in result.evidence
            ],
        }
        (ROOT / ".temp/deepseek-scoped-result.json").write_text(
            result.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        (ROOT / "docs/deepseek-v4-scoped-verification.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report), flush=True)
        return report["passed"]


if __name__ == "__main__":
    raise SystemExit(0 if asyncio.run(main()) else 1)
