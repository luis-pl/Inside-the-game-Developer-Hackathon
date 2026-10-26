"""MCP de composición local por stdio, separado del MCP de consultas deportivas.

No escribe archivos, no abre URLs, no consulta SQL y no invoca modelos. El
anfitrión aporta evidencia autorizada y recibe un HTML o la validación del plan.
"""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolResult,
    ListResourcesResult,
    ListToolsResult,
    ReadResourceResult,
    Resource,
    TextContent,
    TextResourceContents,
    Tool,
)
from pydantic import Field, ValidationError

from inside_game.agents.contracts import Evidence

from .catalog import CATALOG, describe
from .contracts import (
    BlockSpec,
    Closed,
    ReportPlan,
    ReportSpec,
    TeamStyle,
    VisualOptions,
)
from .pages import compile_report, render_report


class Empty(Closed):
    pass


class DescribeRequest(Closed):
    insight_id: str = Field(max_length=80)


class RenderInsightRequest(BlockSpec):
    """Una pieza individual usa el mismo contrato que un bloque de la página.

    El agente aporta parámetros y referencias. El anfitrión conserva los datos
    originales: no hace falta copiar miles de coordenadas al contexto del LLM.
    """

    id: str = Field(default="insight", pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,59}$")
    teams: list[TeamStyle] = Field(default_factory=list, max_length=20)


MODELS = {
    "list_insights": Empty,
    "describe_insight": DescribeRequest,
    "validate_report": ReportPlan,
    "render_insight": RenderInsightRequest,
    "render_report": ReportPlan,
}
DESCRIPTIONS = {
    "list_insights": "Descubre las 30 recetas de insights, operaciones requeridas, variantes y limitaciones.",
    "describe_insight": "Describe una receta aprobada y los esquemas de parámetros y presentación. Selecciona evidence_ids del catálogo; los datos originales los aporta el anfitrión, no esta llamada.",
    "validate_report": "Comprueba referencias, alcance y requisitos de datos. valid indica compatibilidad y ready indica que TODOS los bloques están disponibles. Lee también estados y advertencias; no consulta datos adicionales.",
    "render_insight": "Crea un único gráfico o insight de las 30 recetas: insight_id, evidence_ids, parameters, visual y teams opcionales. Devuelve resource_uri para resources/read; para combinar varios usa render_report. No acepta HTML, SQL ni datos inventados.",
    "render_report": "Genera HTML autocontenido, CSS/SVG/JS incluidos. Devuelve resource_uri, bytes, render_ms y estados; el anfitrión lee el recurso HTML. No copies eventos: usa IDs de evidencia del catálogo.",
}


def referenced_evidence(evidence, blocks):
    """La evidencia declarada por los bloques y el contexto de sus partidos.

    Nunca el catálogo completo. El contexto (`get_match_context`) se conserva
    aunque ningún bloque lo declare: de él salen nombres, dorsales y colores de
    los equipos (`identity.py`); sin él los gráficos dirían "Equipo 105".
    """
    ids = {evidence_id for block in blocks for evidence_id in block.evidence_ids}
    selected = [item for item in evidence if item.evidence_id in ids]
    matches = set()
    for item in selected:
        if item.arguments.get("match_id") is not None:
            matches.add(item.arguments["match_id"])
        matches.update(item.arguments.get("match_ids") or [])
    context = [
        item
        for item in evidence
        if item.operation == "get_match_context"
        and item.evidence_id not in ids
        and item.arguments.get("match_id") in matches
    ]
    return selected + context


def create_server(evidence=(), *, render_options=None):
    """`render_options` son decisiones del anfitrión que el modelo no controla
    (`zero_only_insights`, `unannotated_metrics`): se suman a cada ReportSpec."""
    trusted = [Evidence.model_validate(e) for e in evidence]
    host = dict(render_options or {})
    artifacts = {}
    resource_prefix = "insight://report/" + str(uuid4()) + "/"

    async def list_resources(ctx, params):
        return ListResourcesResult(
            resources=[
                Resource(
                    name="Informe HTML",
                    uri=uri,
                    mimeType="text/html",
                    size=len(html.encode()),
                )
                for uri, html in artifacts.items()
            ]
        )

    async def read_resource(ctx, params):
        uri = str(params.uri)
        if uri not in artifacts:
            raise ValueError("UNKNOWN_REPORT_RESOURCE")
        return ReadResourceResult(
            contents=[
                TextResourceContents(uri=uri, mimeType="text/html", text=artifacts[uri])
            ]
        )

    async def list_tools(ctx, params):
        return ListToolsResult(
            tools=[
                Tool(
                    name=name,
                    description=DESCRIPTIONS[name],
                    input_schema=model.model_json_schema(),
                )
                for name, model in MODELS.items()
            ]
        )

    async def call_tool(ctx, params):
        name = params.name
        try:
            if name not in MODELS:
                raise ValueError("UNKNOWN_TOOL")
            request = MODELS[name].model_validate(params.arguments or {})
            if name == "list_insights":
                result = {
                    **CATALOG,
                    "evidence_catalog": [
                        {
                            "evidence_id": e.evidence_id,
                            "operation": e.operation,
                            "arguments": e.arguments,
                            "scope": e.response.scope,
                            "coverage": e.response.coverage,
                        }
                        for e in trusted
                    ],
                }
            elif name == "describe_insight":
                result = {
                    **describe(request.insight_id),
                    "block_schema": BlockSpec.model_json_schema(),
                    "visual_schema": VisualOptions.model_json_schema(),
                    "usage": "Elige evidence_ids de list_insights. render_insight crea una pieza; render_report combina blocks en una página. Lee el HTML con resources/read.",
                }
            elif name in {"render_insight", "render_report"}:
                if name == "render_insight":
                    plan = {
                        "title": request.title or describe(request.insight_id)["title"],
                        "blocks": [request.model_dump(exclude={"teams"})],
                        "teams": request.teams,
                    }
                else:
                    plan = request.model_dump()
                spec = ReportSpec(
                    **plan,
                    evidence=referenced_evidence(
                        trusted,
                        [request] if name == "render_insight" else request.blocks,
                    ),
                    **host,
                )
                result = await asyncio.to_thread(render_report, spec)
                html = result.pop("html")
                uri = resource_prefix + hashlib.sha256(html.encode()).hexdigest()
                artifacts[uri] = html
                while (
                    len(artifacts) > 4
                    or sum(len(v.encode()) for v in artifacts.values())
                    > 32 * 1024 * 1024
                ):
                    artifacts.pop(next(iter(artifacts)))
                result["resource_uri"] = uri
            else:
                spec = ReportSpec(
                    **request.model_dump(),
                    evidence=referenced_evidence(trusted, request.blocks),
                    **host,
                )
                _, blocks = await asyncio.to_thread(compile_report, spec)
                result = {
                    "valid": all(
                        b.state not in {"incompatible", "error"} for b in blocks
                    ),
                    "ready": all(b.state == "ready" for b in blocks),
                    "blocks": [
                        {"id": b.id, "state": b.state, "warnings": b.warnings}
                        for b in blocks
                    ],
                }
            # No duplicar megabytes de HTML en content y structured_content.
            summary = (
                {k: v for k, v in result.items() if k != "html"}
                if name in {"render_report", "render_insight"}
                else result
            )
            return CallToolResult(
                structured_content=result,
                content=[
                    TextContent(
                        type="text", text=json.dumps(summary, ensure_ascii=False)
                    )
                ],
            )
        except (ValidationError, ValueError):
            return CallToolResult(
                is_error=True,
                content=[
                    TextContent(
                        type="text",
                        text=json.dumps({"error": {"code": "INVALID_INSIGHT_REQUEST"}}),
                    )
                ],
            )

    return Server(
        "inside-game-insights",
        version="1.0.0",
        instructions="Flujo: list_insights descubre recetas y evidencia; describe_insight explica la pieza; validate_report comprueba un plan. render_insight crea una pieza y render_report combina varias. Ambos devuelven resource_uri: usa resources/read para obtener HTML. Pasa parámetros y evidence_ids, no HTML ni SQL ni cifras inventadas. El anfitrión carga la evidencia original del agente de datos al iniciar esta instancia. Estados unavailable/partial y la procedencia (sintética o real) deben permanecer visibles; valid no significa ready. No consulta datos nuevos ni ejecuta un modelo.",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
        on_list_resources=list_resources,
        on_read_resource=read_resource,
    )


async def run(evidence):
    server = create_server(evidence)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence-file",
        type=Path,
        required=True,
        help="Respuesta DataResult confiable o manifiesto del anfitrión",
    )
    args = parser.parse_args()
    try:
        if args.evidence_file.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("EVIDENCE_BUDGET_EXCEEDED")
        evidence = json.loads(args.evidence_file.read_text(encoding="utf-8-sig"))[
            "evidence"
        ]
        asyncio.run(run(evidence))
    except (OSError, ValueError, KeyError):
        parser.exit(1, "Evidencia local no válida; no se inició el MCP de insights.\n")


if __name__ == "__main__":
    main()
