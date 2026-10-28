"""Conversaciones privadas y trabajos observables del intérprete, con memoria acotada."""

import asyncio
import hashlib
import json
import time
from uuid import UUID, uuid4

import httpx
from fastapi import Request
from fastapi.responses import HTMLResponse
from pydantic import Field

from inside_game.agents.analyst_contracts import (
    AnalysisReportResult,
    AnalysisRequest,
    AttachAnalysis,
)
from inside_game.agents.analyst_facts import source_key
from inside_game.agents.contracts import DataContext, DataRequest, DataResult, Message
from inside_game.agents.conversation_copy import (
    catalog_reply,
    concept_reply,
    report_reply,
)
from inside_game.agents.experiments import T
from inside_game.agents.http_client import HttpDataAgent
from inside_game.agents.insight_contracts import InsightRequest
from inside_game.agents.insights_http_client import HttpInsightsAgent, PayloadParser
from inside_game.agents.interpreter import Interpretation, Interpreter
from inside_game.agents.report_changes import describe_changes
from inside_game.agents.report_store import ReportError
from inside_game.agents.sports_analyst import AnalystLimits, SportsAnalyst
from inside_game.contracts import ApiResponse
from inside_game.insights.contracts import AnalystNote
from inside_game.language import Language, wording
from inside_game.providers.models import ModelFailure
from inside_game.tools.mcp_client import DataMcpSettings


class ChatMessage(Message):
    request_id: UUID = Field(default_factory=uuid4)
    language: Language | None = None
    text: str = Field(min_length=1, max_length=4000)
    context: DataContext | None = None
    retry_analysis: bool = False


class Conversations:
    def __init__(self, app, store, model_factory, data_url, insights_url):
        self.app, self.reports, self.model_factory = app, store, model_factory
        self.data_url, self.insights_url = data_url, insights_url
        self.items, self.tasks = {}, set()
        self.catalogs = {}
        self.catalog_locks = {}

    def prune(self):
        now = time.monotonic()
        self.items = {
            k: v for k, v in self.items.items() if v["expires"] > now or v["busy"]
        }
        self.catalogs = {k: v for k, v in self.catalogs.items() if v[0] > now}

    def get(self, owner, cid):
        self.prune()
        value = self.items.get((owner, str(cid)))
        if not value:
            raise ReportError("CONVERSATION_NOT_FOUND", 404)
        return value

    def view(self, value):
        return {k: v for k, v in value.items() if k != "expires"}

    async def catalog(self, owner, key):
        self.prune()
        if owner in self.catalogs:
            return self.catalogs[owner][1]
        # La selección inicial sólo necesita una consulta fija de metadatos.
        # No depende de una inferencia ni compite con el trabajo analítico del chat.
        async with self.catalog_locks.setdefault(owner, asyncio.Lock()):
            if owner in self.catalogs:
                return self.catalogs[owner][1]
            url = (
                DataMcpSettings.from_env().url.removesuffix("/mcp")
                + "/api/operations/list_matches"
            )
            # SQL serverless can wake after the first request has timed out.
            # Retry this fixed read once, within a total deadline; do not disable
            # AutoPause or silently switch to old/fixture data to hide the delay.
            try:
                async with asyncio.timeout(55):
                    result = await self._read_catalog(url, key)
            except (TimeoutError, httpx.HTTPError):
                raise ModelFailure("MATCH_CATALOG_UNAVAILABLE") from None
            rows = result.data.get("items", [])
            if not rows:
                raise ModelFailure("MATCH_CATALOG_UNAVAILABLE")
            allowed = {
                "match_id",
                "home_team_id",
                "home_team_name",
                "away_team_id",
                "away_team_name",
                "is_synthetic",
                "data_kind",
                "provider",
                "home_score",
                "away_score",
            }
            rows = [{k: v for k, v in row.items() if k in allowed} for row in rows]
            self.catalogs[owner] = (time.monotonic() + 300, rows)
            return rows

    async def _read_catalog(self, url, key):
        async with httpx.AsyncClient(
            timeout=25, trust_env=False, follow_redirects=False
        ) as client:
            for attempt in range(2):
                try:
                    async with client.stream(
                        "POST",
                        url,
                        headers={"Authorization": "Bearer " + key},
                        json={"limit": 50},
                    ) as response:
                        if (
                            response.status_code in {429, 502, 503, 504}
                            and attempt == 0
                        ):
                            continue
                        if response.status_code != 200:
                            raise ModelFailure("MATCH_CATALOG_UNAVAILABLE")
                        raw = bytearray()
                        async for chunk in response.aiter_bytes():
                            raw.extend(chunk)
                            if len(raw) > 1024 * 1024:
                                raise ModelFailure("MATCH_CATALOG_TOO_LARGE")
                    try:
                        result = ApiResponse.model_validate_json(raw)
                    except ValueError:
                        raise ModelFailure("INVALID_MATCH_CATALOG") from None
                    if result.operation_id != "list_matches":
                        raise ModelFailure("INVALID_MATCH_CATALOG")
                    return result
                except httpx.TransportError:
                    if attempt:
                        raise
        raise ModelFailure("MATCH_CATALOG_UNAVAILABLE")

    def stage(self, value, stage):
        value["stage"] = stage
        value["events"].append({"stage": stage, "at": round(time.time(), 3)})
        value["events"] = value["events"][-100:]

    async def work(self, owner, key, value, message):
        language = message.language or value.get("language", "es")
        started = time.perf_counter()
        audit = {
            "request_id": str(message.request_id),
            "input": message.model_dump(mode="json"),
        }
        previous_plan = None
        analysis_reused = False
        try:
            async with asyncio.timeout(T(110)):
                if message.retry_analysis:
                    if not value["report"]:
                        raise ModelFailure("REPORT_REQUIRED_FOR_ANALYSIS")
                    matches = []
                    plan = Interpretation(
                        language=language,
                        action="modify",
                        title=value["title"],
                        reply="Completo el análisis del informe disponible.",
                        context=DataContext.model_validate(value["report_context"]),
                        analysis_request=message.text,
                    )
                else:
                    self.stage(value, "catalog")
                    matches = await self.catalog(owner, key)
                    self.stage(value, "interpreting")
                    context = (
                        message.context
                        if message.context is not None
                        else DataContext.model_validate(value["context"])
                    )
                    async with self.model_factory() as model:
                        interpreter = Interpreter(model)
                        try:
                            plan = await interpreter.interpret(
                                text=message.text,
                                context=context,
                                history=value["messages"][:-1],
                                matches=matches,
                                report=value["report"],
                                request_id=message.request_id,
                                language=message.language,
                                previous_language=language,
                            )
                        finally:
                            audit["interpreter_prompt_sha256"] = (
                                interpreter.prompt_sha256
                            )
                            audit["interpreter_tools"] = interpreter.trace
                            audit["interpreter_model_turns"] = interpreter.model_turns
                            audit["interpreter_total_tokens"] = interpreter.total_tokens
                            audit["interpreter_context_events"] = (
                                interpreter.context_window.events
                            )
                audit["delegation"] = plan.model_dump(mode="json")
                language = plan.language
                value["language"] = language
                if plan.context.match_ids:
                    value["context"] = plan.context.model_dump(mode="json")
                if plan.action in {"clarify", "catalog", "answer"}:
                    reply = plan.reply
                    if plan.action == "answer":
                        selected_ids = (
                            message.context.match_ids
                            if message.context is not None
                            else value["context"].get("match_ids", [])
                        )
                        reply = concept_reply(
                            plan.answer_topic,
                            reply,
                            [m for m in matches if m["match_id"] in selected_ids],
                            language=language,
                        )
                    if plan.action == "catalog":
                        reply = catalog_reply(plan.reply, matches, language=language)
                    self.stage(
                        value,
                        "clarification" if plan.action == "clarify" else "complete",
                    )
                else:
                    value["context"] = plan.context.model_dump(mode="json")
                    value["title"] = plan.title
                    client = HttpInsightsAgent(self.insights_url, key)
                    if plan.action == "create":
                        self.stage(value, "data")
                        data = await HttpDataAgent(self.data_url, key).fetch(
                            DataRequest(
                                language=language,
                                original_request=message.text,
                                request_text=plan.data_request,
                                context=plan.context,
                            ),
                            timeout=T(35),
                        )
                        audit["data"] = {
                            **data.model_dump(mode="json", exclude={"evidence"}),
                            "evidence_catalog": [
                                {
                                    "evidence_id": e.evidence_id,
                                    "operation": e.operation,
                                    "arguments": e.arguments,
                                    "source_sha256": hashlib.sha256(
                                        source_key(e).encode()
                                    ).hexdigest(),
                                }
                                for e in data.evidence
                            ],
                        }
                        if not data.evidence:
                            raise ModelFailure(
                                "DATA_AGENT_DEADLINE_EXCEEDED"
                                if any(
                                    i.code == "DEADLINE_EXCEEDED" for i in data.issues
                                )
                                else "DATA_EVIDENCE_UNAVAILABLE"
                            )
                        self.stage(value, "analysis")
                        raw = await client._request(
                            "POST",
                            "/a2a/v1/analysis-reports",
                            timeout=T(56),
                            payload=AnalysisRequest(
                                language=language,
                                original_request=message.text,
                                required_insights=plan.required_insights,
                                request_text=plan.analysis_request,
                                context=plan.context,
                                data_result=data,
                            ).model_dump(mode="json"),
                        )
                        result = AnalysisReportResult.model_validate_json(raw)
                        report, analysis = result.report, result.analysis
                    else:
                        current = value["report"]
                        previous_plan = self.reports.get(
                            owner, current["report_id"]
                        ).result.plan
                        if (
                            plan.context.match_ids
                            != value["report_context"]["match_ids"]
                        ):
                            raise ModelFailure("EDIT_MATCH_CANNOT_CHANGE")
                        handoff = None
                        if plan.data_request.strip():
                            self.stage(value, "data")
                            handoff = await HttpDataAgent(self.data_url, key).fetch(
                                DataRequest(
                                    language=language,
                                    original_request=message.text,
                                    request_text=plan.data_request
                                    + " Recupera sólo lo necesario para esta modificación. En get_rankings usa limit=100 para recuperar este catálogo en una página, no resúmenes jugador por jugador. No repitas tiros o series si ya los aporta el informe.",
                                    context=plan.context,
                                ),
                                timeout=T(25),
                            )
                            audit["data"] = {
                                "request_id": str(handoff.request_id),
                                "status": handoff.status,
                                "issues": [i.model_dump() for i in handoff.issues],
                                "evidence_catalog": [
                                    {
                                        "evidence_id": e.evidence_id,
                                        "operation": e.operation,
                                        "arguments": e.arguments,
                                    }
                                    for e in handoff.evidence
                                ],
                            }
                            if not handoff.evidence:
                                raise ModelFailure("DATA_EVIDENCE_UNAVAILABLE")
                        if message.retry_analysis:
                            existing = self.reports.get(owner, current["report_id"])
                            report = existing.result
                            parser = PayloadParser()
                            parser.feed(report.html)
                            payload = json.loads("".join(parser.parts))
                        else:
                            self.stage(value, "editing")
                            report, payload = await client.preview(
                                InsightRequest(
                                    language=language,
                                    original_request=message.text,
                                    request_text=plan.analysis_request,
                                    context=DataContext.model_validate(
                                        value["report_context"]
                                    ),
                                    report_id=current["report_id"],
                                    expected_revision=current["revision"],
                                    data_result=handoff,
                                    analyst=AnalystNote(
                                        text=wording("updating", language),
                                        evidence_ids=[],
                                    ),
                                ),
                                timeout=min(
                                    T(52),
                                    max(1, T(95) - (time.perf_counter() - started)),
                                ),
                            )
                        analysis = None
                        if report.report_id and payload:
                            value["report"] = {
                                "report_id": str(report.report_id),
                                "revision": report.revision,
                                "blocks": report.blocks,
                                "status": "partial",
                            }
                            # El analista revisa la página modificada, sin crear otra página
                            # ni dejar un texto viejo unido a cifras que hayan cambiado.
                            snapshot = self.reports.get(owner, report.report_id)
                            changes = describe_changes(
                                previous_plan, snapshot.result.plan
                            )
                            value["changes"] = {**changes, "revision": report.revision}
                            # Acotar la lectura a lo que cambió evita volver a enviar
                            # todos los datos y rehacer el análisis de nueve gráficos.
                            focus_ids = set(changes["data_changed_ids"])
                            focus_blocks = [
                                b for b in payload["blocks"] if b["id"] in focus_ids
                            ]
                            if not focus_blocks:
                                focus_blocks = (
                                    payload["blocks"]
                                    if len(payload["blocks"]) <= 4
                                    else payload["blocks"][-3:]
                                )
                            source_ids = {
                                e for b in focus_blocks for e in b["evidence_ids"]
                            }
                            sources = [
                                e
                                for e in snapshot.result.evidence
                                if e.evidence_id in source_ids
                            ]
                            metadata = {
                                e.arguments.get("match_id"): e
                                for e in snapshot.result.evidence
                                if e.operation == "get_match_context"
                            }
                            sources.extend(
                                e
                                for e in metadata.values()
                                if e.evidence_id not in {s.evidence_id for s in sources}
                            )
                            payload = {
                                **payload,
                                "blocks": focus_blocks,
                                "evidence": [
                                    e.model_dump(mode="json") for e in sources
                                ],
                            }
                            payload["evidence_catalog"] = [
                                {
                                    "evidence_id": e.evidence_id,
                                    "source_sha256": hashlib.sha256(
                                        source_key(e).encode()
                                    ).hexdigest(),
                                }
                                for e in sources
                            ]
                            pinned_result = report

                            class CurrentPage:
                                async def preview(self, request, *, timeout):
                                    return pinned_result, payload

                            self.stage(value, "analysis")
                            if (
                                not plan.refresh_analysis
                                and not changes["data_changed_ids"]
                                and not changes["removed"]
                                and previous_plan.analyst
                            ):
                                analysis_reused = True
                                note = previous_plan.analyst.text
                                mapped_ids = previous_plan.analyst.evidence_ids
                            else:
                                async with self.model_factory() as model:
                                    analysis = await SportsAnalyst(
                                        model,
                                        insights_client=CurrentPage(),
                                        limits=AnalystLimits(
                                            timeout_seconds=min(
                                                T(40),
                                                max(
                                                    1,
                                                    T(102)
                                                    - (time.perf_counter() - started),
                                                ),
                                            )
                                        ),
                                    ).run(
                                        AnalysisRequest(
                                            language=language,
                                            original_request=message.text,
                                            request_text="Analiza sólo los bloques suministrados de esta actualización. Tres apartados breves, máximo dos afirmaciones cada uno. Responde a esta intención: "
                                            + message.text
                                            + " No narres cambios de título o tareas de edición. Declara el alcance y las limitaciones.",
                                            context=snapshot.context,
                                            data_result=DataResult(
                                                request_id=uuid4(),
                                                status="complete",
                                                model="original-evidence",
                                                evidence=sources,
                                            ),
                                        )
                                    )
                                note = analysis.text or wording(
                                    "analysis_unavailable", language
                                )
                                aliases = analysis.visual_evidence_aliases
                                ids = list(
                                    dict.fromkeys(
                                        e
                                        for f in analysis.facts
                                        for e in f.evidence_ids
                                    )
                                )
                                mapped_ids = [aliases[e] for e in ids]
                            report = await client.attach(
                                report.report_id,
                                AttachAnalysis(
                                    expected_revision=report.revision,
                                    analyst=AnalystNote(
                                        text=note,
                                        evidence_ids=mapped_ids,
                                    ),
                                ),
                                timeout=8,
                            )
                    audit["analysis"] = (
                        analysis.model_dump(mode="json", exclude={"visual_report"})
                        if analysis
                        else None
                    )
                    audit["insights"] = (
                        report.model_dump(mode="json") if report else None
                    )
                    if not report or not report.artifact_url:
                        reply = (
                            (analysis.clarification or analysis.text)
                            if analysis
                            else report.clarification
                            if report
                            else None
                        )
                        if not reply:
                            raise ModelFailure(
                                report.issues[0]
                                if report and report.issues
                                else "REPORT_NOT_CREATED"
                            )
                        self.stage(
                            value,
                            "clarification"
                            if (analysis and analysis.clarification)
                            or (report and report.clarification)
                            else "partial"
                            if analysis
                            and analysis.status == "partial"
                            and analysis.text
                            else "error",
                        )
                    else:
                        value["report"] = {
                            "report_id": str(report.report_id),
                            "revision": report.revision,
                            "blocks": report.blocks,
                            "status": report.status,
                        }
                        value["report_context"] = value["context"]
                        final_snapshot = self.reports.get(owner, report.report_id)
                        value["changes"] = {
                            **describe_changes(
                                previous_plan, final_snapshot.result.plan
                            ),
                            "revision": report.revision,
                        }
                        audit["changes"] = value["changes"]
                        audit["analysis_reused"] = analysis_reused
                        partial = report.status != "complete" or (
                            not analysis_reused
                            and (not analysis or analysis.status != "complete")
                        )
                        self.stage(value, "partial" if partial else "complete")
                        reply = report_reply(
                            analysis,
                            reused=analysis_reused,
                            partial=partial,
                            language=language,
                        )
                value["messages"].append({"role": "assistant", "content": reply})
                if (
                    value["stage"] == "partial"
                    and value["report"]
                    and not analysis_reused
                ):
                    value["messages"][-1]["retry_analysis"] = bool(
                        not analysis or analysis.status == "error"
                    )
        except (TimeoutError, ModelFailure, ReportError, ValueError) as exc:
            code = getattr(
                exc,
                "code",
                "CHAT_DEADLINE_EXCEEDED"
                if isinstance(exc, TimeoutError)
                else "CHAT_INVALID_RESULT",
            )
            audit["error"] = code
            self.stage(value, "error")
            value["messages"].append(
                {
                    "role": "assistant",
                    "content": (
                        wording("timeout", language)
                        if "TIMEOUT" in code or "DEADLINE" in code
                        else wording("failed", language)
                    ),
                    "error": code,
                    "retry_analysis": bool(
                        value.get("report", {})
                        and value["report"].get("status") == "partial"
                    ),
                }
            )
        except Exception:  # noqa: BLE001 -- Límite de tarea: nunca exponer cuerpos del proveedor.
            audit["error"] = "CHAT_EXECUTION_FAILED"
            self.stage(value, "error")
            value["messages"].append(
                {
                    "role": "assistant",
                    "content": wording("interrupted", language),
                    "error": "CHAT_EXECUTION_FAILED",
                }
            )
        finally:
            audit["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
            value["runs"].append(audit)
            value["runs"] = value["runs"][-3:]
            value["busy"] = False
            value["expires"] = time.monotonic() + 3600


def register_chat_routes(app, *, store, model_factory, data_url, insights_url):
    engine = Conversations(app, store, model_factory, data_url, insights_url)
    app.state.chat = engine

    @app.get("/a2a/v1/conversations")
    async def listing(request: Request):
        engine.prune()
        return [
            {"id": cid, "title": v["title"], "busy": v["busy"]}
            for (owner, cid), v in engine.items.items()
            if owner == request.state.principal.id
        ]

    @app.post("/a2a/v1/conversations")
    async def create(request: Request):
        owner = request.state.principal.id
        engine.prune()
        if len(engine.items) >= 200 or sum(k[0] == owner for k in engine.items) >= 20:
            raise ReportError("CONVERSATION_LIMIT_REACHED", 429)
        cid = str(uuid4())
        engine.items[owner, cid] = {
            "id": cid,
            "title": "Nuevo análisis",
            "messages": [],
            "context": DataContext().model_dump(mode="json"),
            "report_context": {},
            "report": None,
            "busy": False,
            "stage": "idle",
            "events": [],
            "runs": [],
            "request_ids": {},
            "expires": time.monotonic() + 3600,
        }
        return engine.view(engine.items[owner, cid])

    @app.get("/a2a/v1/chat-catalog")
    async def catalog(request: Request):
        try:
            return {
                "matches": await engine.catalog(
                    request.state.principal.id, request.headers["authorization"][7:]
                )
            }
        except ModelFailure as exc:
            raise ReportError(exc.code, 503) from None

    @app.get("/a2a/v1/conversations/{cid}")
    async def get(cid: UUID, request: Request):
        return engine.view(engine.get(request.state.principal.id, cid))

    @app.post("/a2a/v1/conversations/{cid}/messages", status_code=202)
    async def send(cid: UUID, message: ChatMessage, request: Request):
        value = engine.get(request.state.principal.id, cid)
        digest = hashlib.sha256(message.model_dump_json().encode()).hexdigest()
        old = value["request_ids"].get(str(message.request_id))
        if old:
            if old != digest:
                raise ReportError("REQUEST_ID_REUSED")
            return engine.view(value)
        if not message.text.strip():
            raise ReportError("EMPTY_MESSAGE", 422)
        if value["busy"]:
            raise ReportError("CONVERSATION_BUSY")
        if len(value["messages"]) >= 60 or len(engine.tasks) >= 4:
            raise ReportError("CHAT_CAPACITY_REACHED", 429)
        value["request_ids"][str(message.request_id)] = digest
        value["busy"] = True
        value["started_at"] = time.time()
        value["messages"].append({"role": "user", "content": message.text})
        engine.stage(value, "queued")
        task = asyncio.create_task(
            engine.work(
                request.state.principal.id,
                request.headers["authorization"][7:],
                value,
                message,
            )
        )
        engine.tasks.add(task)
        task.add_done_callback(engine.tasks.discard)
        return engine.view(value)

    @app.get("/a2a/v1/conversations/{cid}/page", response_class=HTMLResponse)
    async def page(cid: UUID, request: Request):
        value = engine.get(request.state.principal.id, cid)
        if not value["report"]:
            raise ReportError("REPORT_NOT_FOUND", 404)
        result = store.get(
            request.state.principal.id,
            value["report"]["report_id"],
            value["report"]["revision"],
        ).result
        return HTMLResponse(result.html)
