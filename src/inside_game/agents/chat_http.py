"""Conversaciones privadas y trabajos observables del intérprete, con memoria acotada."""

import asyncio
import hashlib
import time
from uuid import UUID, uuid4

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
from inside_game.agents.http_client import HttpDataAgent
from inside_game.agents.insight_contracts import InsightRequest
from inside_game.agents.insights_http_client import HttpInsightsAgent
from inside_game.agents.interpreter import Interpreter
from inside_game.agents.report_store import ReportError
from inside_game.agents.sports_analyst import SportsAnalyst
from inside_game.insights.contracts import AnalystNote
from inside_game.providers.models import ModelFailure


class ChatMessage(Message):
    request_id: UUID = Field(default_factory=uuid4)
    text: str = Field(min_length=1, max_length=4000)
    context: DataContext | None = None


class Conversations:
    def __init__(self, app, store, model_factory, data_url, insights_url):
        self.app, self.reports, self.model_factory = app, store, model_factory
        self.data_url, self.insights_url = data_url, insights_url
        self.items, self.tasks = {}, set()
        self.catalogs = {}

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
        result = await HttpDataAgent(self.data_url, key).fetch(
            DataRequest(
                request_text="Ejecuta únicamente list_matches, limit 50, todos los partidos disponibles reales y sintéticos. No más operaciones."
            ),
            timeout=35,
        )
        rows = [
            row
            for e in result.evidence
            if e.operation == "list_matches"
            for row in e.response.data.get("items", [])
        ]
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

    def stage(self, value, stage):
        value["stage"] = stage
        value["events"].append({"stage": stage, "at": round(time.time(), 3)})
        value["events"] = value["events"][-100:]

    async def work(self, owner, key, value, message):
        started = time.perf_counter()
        audit = {
            "request_id": str(message.request_id),
            "input": message.model_dump(mode="json"),
        }
        try:
            async with asyncio.timeout(110):
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
                        )
                    finally:
                        audit["interpreter_prompt_sha256"] = interpreter.prompt_sha256
                        audit["interpreter_tools"] = interpreter.trace
                audit["delegation"] = plan.model_dump(mode="json")
                if plan.context.match_ids:
                    value["context"] = plan.context.model_dump(mode="json")
                if plan.action in {"clarify", "catalog"}:
                    reply = plan.reply
                    if plan.action == "catalog":
                        reply = "Partidos disponibles:\n" + "\n".join(
                            f"{m['match_id']} · {m.get('home_team_name', '?')} — {m.get('away_team_name', '?')}"
                            for m in matches
                        )
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
                                request_text=plan.data_request, context=plan.context
                            ),
                            timeout=35,
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
                            raise ModelFailure("DATA_EVIDENCE_UNAVAILABLE")
                        self.stage(value, "analysis")
                        raw = await client._request(
                            "POST",
                            "/a2a/v1/analysis-reports",
                            timeout=56,
                            payload=AnalysisRequest(
                                request_text=plan.analysis_request,
                                context=plan.context,
                                data_result=data,
                            ).model_dump(mode="json"),
                        )
                        result = AnalysisReportResult.model_validate_json(raw)
                        report, analysis = result.report, result.analysis
                    else:
                        current = value["report"]
                        if (
                            plan.context.match_ids
                            != value["report_context"]["match_ids"]
                        ):
                            raise ModelFailure("EDIT_MATCH_CANNOT_CHANGE")
                        self.stage(value, "editing")
                        report, payload = await client.preview(
                            InsightRequest(
                                request_text=plan.analysis_request,
                                context=DataContext.model_validate(
                                    value["report_context"]
                                ),
                                report_id=current["report_id"],
                                expected_revision=current["revision"],
                                analyst=AnalystNote(
                                    text="Análisis en actualización.", evidence_ids=[]
                                ),
                            ),
                            timeout=40,
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
                            payload["evidence_catalog"] = [
                                {
                                    "evidence_id": e.evidence_id,
                                    "source_sha256": hashlib.sha256(
                                        source_key(e).encode()
                                    ).hexdigest(),
                                }
                                for e in snapshot.result.evidence
                            ]
                            pinned_result = report

                            class CurrentPage:
                                async def preview(self, request, *, timeout):
                                    return pinned_result, payload

                            self.stage(value, "analysis")
                            async with self.model_factory() as model:
                                analysis = await SportsAnalyst(
                                    model, insights_client=CurrentPage()
                                ).run(
                                    AnalysisRequest(
                                        request_text="Analiza sólo los gráficos de esta página actualizada, con referencias y límites. "
                                        + plan.analysis_request,
                                        context=snapshot.context,
                                        data_result=DataResult(
                                            request_id=uuid4(),
                                            status="complete",
                                            model="original-evidence",
                                            evidence=snapshot.result.evidence,
                                        ),
                                    )
                                )
                            note = (
                                analysis.text
                                or "No se pudo actualizar el análisis; consulta los gráficos y su procedencia."
                            )
                            aliases = analysis.visual_evidence_aliases
                            ids = list(
                                dict.fromkeys(
                                    e for f in analysis.facts for e in f.evidence_ids
                                )
                            )
                            report = await client.attach(
                                report.report_id,
                                AttachAnalysis(
                                    expected_revision=report.revision,
                                    analyst=AnalystNote(
                                        text=note,
                                        evidence_ids=[aliases[e] for e in ids],
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
                            else None
                        )
                        if not reply:
                            raise ModelFailure("REPORT_NOT_CREATED")
                        self.stage(
                            value,
                            "clarification"
                            if analysis and analysis.clarification
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
                        partial = (
                            report.status != "complete"
                            or not analysis
                            or analysis.status != "complete"
                        )
                        self.stage(value, "partial" if partial else "complete")
                        reply = (
                            ("Actualicé" if plan.action == "modify" else "Creé")
                            + f" la página con {len(report.blocks)} gráficos y la lectura del analista."
                        )
                        if partial:
                            reply += " Hay límites o resultados parciales: revísalos en el informe."
                value["messages"].append({"role": "assistant", "content": reply})
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
                    "content": "No pude completar esta petición. Puedes reintentarlo; la página anterior sigue disponible.",
                    "error": code,
                }
            )
        except Exception:  # noqa: BLE001 -- Límite de tarea: nunca exponer cuerpos del proveedor.
            audit["error"] = "CHAT_EXECUTION_FAILED"
            self.stage(value, "error")
            value["messages"].append(
                {
                    "role": "assistant",
                    "content": "La ejecución se interrumpió. Puedes volver a intentarlo.",
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
