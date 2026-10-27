"""Mensajes agénticos por HTTP v1; protocolo propio, no certificación A2A.

Cada titular conserva su identidad al delegar a data y al MCP deportivo. La
intención nunca configura URLs, herramientas, modelo, límites o credenciales.
"""

import asyncio
import hashlib
import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import replace
from uuid import UUID

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from inside_game.access import KeyRegistry
from inside_game.agents.analyst_facts import source_key
from inside_game.agents.contracts import (
    AgentIssue,
    DataContext,
    DataRequest,
    DataResult,
)
from inside_game.agents.dashboard_builder import DashboardBuilder, InsightLimits
from inside_game.agents.data_agent import AgentLimits, DataAgent
from inside_game.agents.http_client import HttpDataAgent
from inside_game.agents.insight_contracts import InsightRequest, InsightResult
from inside_game.agents.report_store import ReportError, ReportStore
from inside_game.providers.models import create_model
from inside_game.tools.mcp_client import DataMcpSettings, connect_data_mcp

log = logging.getLogger("inside_game.agent_audit")
MAX_BODY = 8 * 1024 * 1024


class AgentGuard:
    def __init__(self, app, registry, rate=60):
        self.app, self.registry, self.rate = app, registry, rate
        self.history = defaultdict(deque)
        self.active = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] == "/health":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        auth = headers.get(b"authorization", b"").decode("latin-1")
        principal = self.registry.verify(
            auth[7:] if auth.lower().startswith("bearer ") else ""
        )

        async def reject(code, status):
            return await JSONResponse(
                {"error": {"code": code}},
                status_code=status,
                headers={"Cache-Control": "no-store"},
            )(scope, receive, send)

        if principal is None:
            return await reject("UNAUTHORIZED", 401)
        now = time.monotonic()
        history = self.history[principal.id]
        while history and history[0] < now - 60:
            history.popleft()
        if len(history) >= self.rate or self.active >= 8:
            return await reject("RATE_LIMITED", 429)
        history.append(now)
        self.active += 1
        status = 500
        try:
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > MAX_BODY:
                    return await reject("BODY_TOO_LARGE", 413)
                if not message.get("more_body", False):
                    break
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body)}
                return await receive()

            async def secure_send(message):
                nonlocal status
                if message["type"] == "http.response.start":
                    status = message["status"]
                    message.setdefault("headers", []).extend(
                        [
                            (b"cache-control", b"no-store"),
                            (b"x-content-type-options", b"nosniff"),
                        ]
                    )
                await send(message)

            scope.setdefault("state", {})["principal"] = principal
            await self.app(scope, replay, secure_send)
        finally:
            self.active -= 1
            log.info(
                json.dumps(
                    {
                        "event": "agent_http",
                        "principal": principal.id,
                        "path": scope["path"],
                        "status": status,
                        "elapsed_ms": round((time.monotonic() - now) * 1000),
                    }
                )
            )


def create_agent_app(
    *,
    credentials,
    data_base_url="http://127.0.0.1:8085",
    model_factory=create_model,
    data_runner=None,
    data_transport=None,
    insights_base_url=None,
    insights_transport=None,
    store=None,
    allowed_hosts=("localhost", "127.0.0.1", "testserver"),
):
    registry = KeyRegistry(credentials)
    if not registry.entries:
        raise ValueError("INDIVIDUAL_AGENT_CREDENTIALS_REQUIRED")
    store = store or ReportStore()
    app = FastAPI(
        title="Inside the game · Agentes HTTP",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
    )
    app.state.store = store
    app.state.registry = registry
    app.add_middleware(AgentGuard, registry=registry)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts))

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return JSONResponse(
            {
                "error": {
                    "code": "INVALID_AGENT_MESSAGE",
                    "fields": [list(e["loc"]) for e in exc.errors()],
                }
            },
            status_code=422,
        )

    @app.exception_handler(ReportError)
    async def report_error(request, exc):
        return JSONResponse({"error": {"code": exc.code}}, status_code=exc.status)

    @app.get("/health")
    async def health():
        return {"status": "ok", "protocol": "inside-game-agent-http-v1"}

    @app.post("/a2a/v1/data")
    async def data(
        message: DataRequest,
        request: Request,
        x_agent_deadline_ms: int = Header(default=40000, ge=1000, le=45000),
    ):
        key = request.headers["authorization"][7:]
        try:
            async with asyncio.timeout(x_agent_deadline_ms / 1000):
                if data_runner:
                    result = await data_runner(message, key, x_agent_deadline_ms / 1000)
                else:
                    settings = replace(DataMcpSettings.from_env(), key=key)
                    async with (
                        model_factory() as model,
                        connect_data_mcp(settings) as mcp,
                    ):
                        result = await DataAgent(
                            model,
                            limits=AgentLimits(
                                timeout_seconds=x_agent_deadline_ms / 1000
                            ),
                        ).run(message, mcp)
        except TimeoutError:
            result = DataResult(
                request_id=message.request_id,
                status="error",
                model="configured",
                issues=[AgentIssue(code="DEADLINE_EXCEEDED")],
            )
        payload = result.model_dump(mode="json")
        if len(json.dumps(payload).encode()) > MAX_BODY:
            return JSONResponse(
                {"error": {"code": "DATA_RESULT_TOO_LARGE"}}, status_code=413
            )
        return JSONResponse(payload, headers={"X-Request-ID": str(message.request_id)})

    @app.post("/a2a/v1/insights")
    async def insights(
        message: InsightRequest,
        request: Request,
        x_agent_deadline_ms: int = Header(default=55000, ge=1000, le=55000),
    ):
        owner = request.state.principal.id
        digest = hashlib.sha256(message.model_dump_json().encode()).hexdigest()
        cached = store.begin(owner, message.request_id, digest)
        if cached:
            return JSONResponse(
                cached.model_dump(mode="json"),
                headers={"X-Request-ID": str(message.request_id)},
            )
        try:
            previous = None
            if message.report_id:
                previous = store.get(owner, message.report_id)
                if previous.result.revision != message.expected_revision:
                    raise ReportError("REVISION_CONFLICT")
                if (
                    message.context.match_ids
                    and message.context.match_ids != previous.context.match_ids
                ):
                    raise ReportError("REPORT_MATCH_CANNOT_CHANGE")
                # Una modificación no pierde el contexto aunque sólo diga
                # "añade Voronoi" o "cambia el color del visitante".
                context = DataContext.model_validate(
                    {
                        **previous.context.model_dump(mode="json"),
                        **message.context.model_dump(mode="json", exclude_unset=True),
                    }
                )
                message = message.model_copy(update={"context": context})
            client = HttpDataAgent(
                data_base_url,
                request.headers["authorization"][7:],
                transport=data_transport,
            )
            try:
                async with asyncio.timeout(x_agent_deadline_ms / 1000):
                    async with model_factory() as model:
                        result = await DashboardBuilder(
                            model,
                            data_client=client,
                            limits=InsightLimits(
                                timeout_seconds=x_agent_deadline_ms / 1000
                            ),
                        ).run(
                            message,
                            previous_plan=previous.result.plan if previous else None,
                            previous_evidence=previous.result.evidence
                            if previous
                            else (),
                        )
            except TimeoutError:
                result = InsightResult(
                    request_id=message.request_id,
                    status="error",
                    model="configured",
                    issues=["DEADLINE_EXCEEDED"],
                )
            if result.html:
                result = await store.publish(owner, message, result)
            store.finish(owner, result)
            return JSONResponse(
                result.model_dump(mode="json"),
                headers={"X-Request-ID": str(message.request_id)},
            )
        except BaseException:
            store.abort(owner, message.request_id)
            raise

    @app.get("/a2a/v1/reports/{report_id}")
    async def report(report_id: UUID, request: Request):
        snapshot = store.get(request.state.principal.id, report_id)
        return {
            **snapshot.result.model_dump(mode="json"),
            "plan": snapshot.result.plan.model_dump(mode="json"),
            "evidence_catalog": [
                {
                    "evidence_id": e.evidence_id,
                    "source_sha256": hashlib.sha256(source_key(e).encode()).hexdigest(),
                }
                for e in snapshot.result.evidence
            ],
        }

    @app.get(
        "/a2a/v1/reports/{report_id}/revisions/{revision}/html",
        response_class=HTMLResponse,
    )
    async def artifact(report_id: UUID, revision: int, request: Request):
        snapshot = store.get(request.state.principal.id, report_id, revision)
        return HTMLResponse(
            snapshot.result.html,
            headers={
                "Content-Disposition": f'inline; filename="report-{report_id}-r{revision}.html"'
            },
        )

    from inside_game.agents.analyst_http import register_analyst_routes

    register_analyst_routes(
        app,
        store=store,
        model_factory=model_factory,
        data_url=data_base_url,
        insights_url=insights_base_url or data_base_url,
        data_transport=data_transport,
        insights_transport=insights_transport,
    )
    from inside_game.agents.chat_http import register_chat_routes

    register_chat_routes(
        app,
        store=store,
        model_factory=model_factory,
        data_url=data_base_url,
        insights_url=insights_base_url or data_base_url,
    )
    return app
