"""Rutas autenticadas del analista y composición final sin regenerar gráficos."""

import asyncio
import hashlib
import time
from uuid import UUID

from fastapi import Header, Request
from fastapi.responses import JSONResponse
from mcp import Client

from inside_game.agents.analyst_contracts import (
    AnalysisReportResult,
    AnalysisRequest,
    AnalysisResult,
    AttachAnalysis,
)
from inside_game.agents.http_client import HttpDataAgent
from inside_game.agents.insight_contracts import InsightRequest
from inside_game.agents.insights_http_client import HttpInsightsAgent
from inside_game.agents.report_store import ReportError
from inside_game.agents.sports_analyst import AnalystLimits, SportsAnalyst
from inside_game.insights.mcp_server import create_server
from inside_game.providers.models import ModelFailure


def register_analyst_routes(
    app,
    *,
    store,
    model_factory,
    data_url,
    insights_url,
    data_transport=None,
    insights_transport=None,
):
    @app.post("/a2a/v1/reports/{report_id}/analysis")
    async def attach(report_id: UUID, message: AttachAnalysis, request: Request):
        owner = request.state.principal.id
        digest = hashlib.sha256(
            ("attach:" + str(report_id) + message.model_dump_json()).encode()
        ).hexdigest()
        cached = store.begin(owner, message.request_id, digest)
        if cached:
            return JSONResponse(cached.model_dump(mode="json"))
        try:
            snapshot = store.get(owner, report_id)
            previous = snapshot.result
            if previous.revision != message.expected_revision:
                raise ReportError("REVISION_CONFLICT")
            plan = previous.plan.model_copy(
                update={"analyst": message.analyst}, deep=True
            )
            async with (
                asyncio.timeout(8),
                Client(create_server(previous.evidence)) as mcp,
            ):
                rendered = await mcp.call_tool(
                    "render_report", plan.model_dump(mode="json")
                )
                if rendered.is_error:
                    raise ReportError("INVALID_ANALYST_REFERENCES", 422)
                content = rendered.structured_content
                resource = await mcp.read_resource(content["resource_uri"])
                html = resource.contents[0].text
            # El plan anterior sólo cambia su nota; no interviene otro LLM.
            result = previous.model_copy(
                update={
                    "request_id": message.request_id,
                    "plan": plan,
                    "html": html,
                    "blocks": content["blocks"],
                },
                deep=True,
            )
            publication = InsightRequest(
                request_id=message.request_id,
                request_text="Adjuntar el texto validado del analista",
                context=snapshot.context,
                report_id=report_id,
                expected_revision=message.expected_revision,
                analyst=message.analyst,
            )
            result = await store.publish(owner, publication, result)
            store.finish(owner, result)
            return JSONResponse(result.model_dump(mode="json"))
        except BaseException:
            store.abort(owner, message.request_id)
            raise

    async def execute(message, request, compose, deadline):
        owner = request.state.principal.id
        digest = hashlib.sha256(
            (
                ("analysis-report:" if compose else "analysis:")
                + message.model_dump_json()
            ).encode()
        ).hexdigest()
        cached = store.begin(owner, message.request_id, digest)
        if cached:
            return JSONResponse(cached.model_dump(mode="json"))
        started = time.monotonic()
        key = request.headers["authorization"][7:]
        data = HttpDataAgent(data_url, key, transport=data_transport)
        insights = HttpInsightsAgent(insights_url, key, transport=insights_transport)
        try:
            report = None
            analysis = None
            try:
                async with asyncio.timeout(deadline):
                    async with model_factory() as model:
                        analysis = await SportsAnalyst(
                            model,
                            data_client=data,
                            insights_client=insights,
                            limits=AnalystLimits(
                                timeout_seconds=max(
                                    0.1, deadline - (8 if compose else 0)
                                )
                            ),
                        ).run(message)
                    if (
                        compose
                        and analysis.text
                        and analysis.visual_report
                        and analysis.visual_report.report_id
                    ):
                        ids = list(
                            dict.fromkeys(
                                e for f in analysis.facts for e in f.evidence_ids
                            )
                        )
                        if any(
                            key not in analysis.visual_evidence_aliases for key in ids
                        ):
                            raise ModelFailure("ANALYST_REFERENCE_NOT_IN_REPORT")
                        mapped = [analysis.visual_evidence_aliases[key] for key in ids]
                        from inside_game.insights.contracts import AnalystNote

                        report = await insights.attach(
                            analysis.visual_report.report_id,
                            AttachAnalysis(
                                expected_revision=analysis.visual_report.revision,
                                analyst=AnalystNote(
                                    text=analysis.text, evidence_ids=mapped
                                ),
                            ),
                            timeout=max(0.01, deadline - (time.monotonic() - started)),
                        )
            except (TimeoutError, ModelFailure) as exc:
                code = (
                    exc.code if isinstance(exc, ModelFailure) else "DEADLINE_EXCEEDED"
                )
                if analysis is not None and analysis.text:
                    analysis = analysis.model_copy(
                        update={
                            "status": "partial",
                            "issues": [*analysis.issues, code],
                            "limitations": [
                                *analysis.limitations,
                                "El texto está disponible, pero no se pudo publicar la página final.",
                            ],
                        },
                        deep=True,
                    )
                else:
                    analysis = AnalysisResult(
                        request_id=message.request_id,
                        status="error",
                        model="configured",
                        issues=[
                            exc.code
                            if isinstance(exc, ModelFailure)
                            else "DEADLINE_EXCEEDED"
                        ],
                    )
            result = (
                AnalysisReportResult(
                    request_id=message.request_id, analysis=analysis, report=report
                )
                if compose
                else analysis
            )
            store.finish(owner, result)
            return JSONResponse(
                result.model_dump(mode="json"),
                headers={"X-Request-ID": str(message.request_id)},
            )
        except BaseException:
            store.abort(owner, message.request_id)
            raise

    @app.post("/a2a/v1/analysis")
    async def analyze(
        message: AnalysisRequest,
        request: Request,
        x_agent_deadline_ms: int = Header(default=55000, ge=1000, le=55000),
    ):
        return await execute(message, request, False, x_agent_deadline_ms / 1000)

    @app.post("/a2a/v1/analysis-reports")
    async def analysis_report(
        message: AnalysisRequest,
        request: Request,
        x_agent_deadline_ms: int = Header(default=55000, ge=1000, le=55000),
    ):
        return await execute(message, request, True, x_agent_deadline_ms / 1000)
