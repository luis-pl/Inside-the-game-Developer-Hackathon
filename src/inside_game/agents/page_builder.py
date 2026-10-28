"""Intención + evidencia -> tools MCP -> página; nunca código escrito por LLM."""

import asyncio
import hashlib
import json
import sysconfig
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from mcp import Client
from pydantic import ValidationError

from inside_game.agents.context_window import ContextWindow
from inside_game.agents.contracts import DataRequest, DataResult, Evidence
from inside_game.agents.data_agent import preview
from inside_game.agents.evidence_pages import include_query_pages
from inside_game.agents.experiments import T, experiment, requested_visuals
from inside_game.agents.insight_contracts import (
    FinishInsight,
    InsightRequest,
    InsightResult,
    ReportChanges,
    RetrieveData,
)
from inside_game.insights.contracts import ReportPlan
from inside_game.insights.mcp_server import (
    DESCRIPTIONS,
    MODELS,
    RenderInsightRequest,
    create_server,
)
from inside_game.providers.models import ModelFailure

RECIPE_SOURCES = {
    item["id"]: item.get("source_operations", [])
    for item in json.loads(
        (Path(__file__).resolve().parents[1] / "insights/catalog.json").read_text(
            encoding="utf-8"
        )
    )["insights"]
}


@dataclass(frozen=True)
class InsightLimits:
    timeout_seconds: float = T(55)
    max_turns: int = 6
    max_tool_calls: int = 10
    max_input_bytes: int = 180000
    max_evidence_bytes: int = 8 * 1024 * 1024

    def __post_init__(self):
        if not 0 < self.timeout_seconds < T(60) or any(
            v <= 0 for v in self.__dict__.values()
        ):
            raise ValueError("INSIGHT_LIMITS_INVALID")


def load_prompt():
    local = Path(__file__).resolve().parents[3] / "prompts/insights_agent.md"
    installed = (
        Path(sysconfig.get_path("data")) / "share/inside-game/prompts/insights_agent.md"
    )
    return (local if local.is_file() else installed).read_text(encoding="utf-8")


class DashboardBuilder:
    def __init__(self, model, *, data_client=None, limits=None, prompt=None):
        self.model, self.data_client = model, data_client
        self.limits = limits or InsightLimits()
        self.prompt = prompt if prompt is not None else load_prompt()

    async def run(self, request, *, previous_plan=None, previous_evidence=()):
        request = InsightRequest.model_validate(request)
        run = _InsightRun(self, request, previous_plan, previous_evidence)
        try:
            async with asyncio.timeout(self.limits.timeout_seconds):
                return await run.execute()
        except TimeoutError:
            return run.result("error", issues=["DEADLINE_EXCEEDED"])
        except ModelFailure as exc:
            return run.result("error", issues=[exc.code])
        except (ValueError, ValidationError):
            return run.result("error", issues=["INVALID_INSIGHT_DATA"])
        except Exception:  # noqa: BLE001 - no exponer cuerpos/cabeceras del proveedor.
            return run.result("error", issues=["INSIGHT_EXECUTION_FAILED"])


class _InsightRun:
    def __init__(self, agent, request, previous_plan, previous_evidence):
        self.agent, self.request = agent, request
        self.previous = (
            ReportPlan.model_validate(previous_plan) if previous_plan else None
        )
        self.evidence = [Evidence.model_validate(e) for e in previous_evidence]
        self.turns = self.calls = self.tokens = self.fetches = 0
        self.started = time.perf_counter()
        self.timings = {"model": 0.0, "data_http": 0.0, "mcp": 0.0}
        self.data_request_ids = []
        self.data_runs = []
        self.trace = []
        self.context_window = ContextWindow(agent.limits.max_input_bytes)
        self.observations = {}
        self.data_partial = False
        self.analyst = request.analyst or (
            self.previous.analyst if self.previous else None
        )

    def merge(self, result):
        """No confundir consultas/páginas que comparten q1 entre DataResults."""
        self.fetches += 1
        self.data_request_ids.append(result.request_id)
        self.data_runs.append(
            {
                "request_id": str(result.request_id),
                "status": result.status,
                "issues": [i.model_dump() for i in result.issues],
                "clarification": result.clarification,
                "notes": result.notes,
                "notes_are_model_text": True,
                "model_turns": result.model_turns,
                "tool_calls": result.tool_calls,
            }
        )
        self.data_partial |= result.status != "complete"
        aliases = {}
        for original in result.evidence:
            existing = next(
                (e for e in self.evidence if e.evidence_id == original.evidence_id),
                None,
            )
            item = original.model_copy(deep=True)
            if (
                existing
                and existing.response == item.response
                and existing.arguments == item.arguments
            ):
                aliases[original.evidence_id] = existing.evidence_id
                continue
            if existing:
                item.evidence_id = f"data-{result.request_id.hex}-{item.evidence_id}"
            aliases[original.evidence_id] = item.evidence_id
            duplicate = next(
                (e for e in self.evidence if e.evidence_id == item.evidence_id), None
            )
            if duplicate:
                if (
                    duplicate.response != item.response
                    or duplicate.arguments != item.arguments
                ):
                    raise ValueError("CONFLICTING_EVIDENCE")
                continue
            item.query_id = f"data-{result.request_id.hex}-{item.query_id}"
            self.evidence.append(item)
        if (
            len(self.evidence) > 100
            or len(
                json.dumps([e.model_dump(mode="json") for e in self.evidence]).encode()
            )
            > self.agent.limits.max_evidence_bytes
        ):
            raise ValueError("EVIDENCE_BUDGET_EXCEEDED")
        return aliases

    def result(self, status, **kwargs):
        return InsightResult(
            request_id=self.request.request_id,
            status=status,
            model=self.agent.model.name,
            model_turns=self.turns,
            tool_calls=self.calls,
            tool_trace=self.trace,
            total_tokens=self.tokens,
            context_events=self.context_window.events,
            elapsed_ms=round((time.perf_counter() - self.started) * 1000, 3),
            timings_ms={k: round(v, 3) for k, v in self.timings.items()},
            data_request_ids=self.data_request_ids,
            data_runs=self.data_runs,
            prompt_sha256=hashlib.sha256(self.agent.prompt.encode()).hexdigest(),
            evidence=self.evidence,
            **kwargs,
        )

    def catalog(self):
        return [
            {
                "evidence_id": e.evidence_id,
                "operation": e.operation,
                "arguments": e.arguments,
                "scope": e.response.scope,
                "provenance": e.response.provenance,
                "coverage": e.response.coverage,
                "warnings": e.response.warnings,
                "coordinates": e.response.coordinates,
                "method_id": e.response.method_id,
                "preview": preview(e.response.data, list_limit=2),
            }
            for e in self.evidence
        ]

    def checkpoint(self):
        return {
            "request_id": str(self.request.request_id),
            "request": self.request.model_dump(mode="json", exclude={"data_result"}),
            "previous_plan": self.previous.model_dump(mode="json")
            if self.previous
            else None,
            "evidence_catalog": self.catalog(),
            "data_partial": self.data_partial,
            "tool_observations": list(self.observations.values()),
            "remaining_seconds": max(
                0,
                self.agent.limits.timeout_seconds
                - (time.perf_counter() - self.started),
            ),
        }

    async def execute(self):
        if self.request.data_result:
            aliases = self.merge(self.request.data_result)
            if self.analyst:
                self.analyst = self.analyst.model_copy(
                    update={
                        "evidence_ids": [
                            aliases.get(key, key) for key in self.analyst.evidence_ids
                        ]
                    }
                )
        if self.request.report_id and not self.previous:
            return self.result("error", issues=["PREVIOUS_REPORT_REQUIRED"])
        functions = []
        async with Client(create_server(self.evidence)) as client:
            for t in (await client.list_tools()).tools:
                if (
                    t.name in MODELS
                    and t.input_schema == MODELS[t.name].model_json_schema()
                ):
                    functions.append(
                        {
                            "type": "function",
                            "name": t.name,
                            "description": DESCRIPTIONS[t.name],
                            "parameters": t.input_schema,
                            "strict": False,
                        }
                    )
        for name, contract, description in [
            (
                "request_data",
                RetrieveData,
                "Pide evidencia adicional a data por HTTP. Sin URL, SQL ni claves. Conserva IDs y alcance; agrupa lo que falta.",
            ),
            (
                "finish_insight_request",
                FinishInsight,
                "Pide aclaración o explica una intención no soportada. Para entregar una página usa render_report/render_insight.",
            ),
            (
                "update_report",
                ReportChanges,
                "Sólo para páginas existentes: patch con add_blocks, replace_blocks, remove_block_ids, order_ids, teams o title. Conserva automáticamente los bloques no afectados y renderiza por MCP.",
            ),
        ]:
            functions.append(
                {
                    "type": "function",
                    "name": name,
                    "description": description,
                    "parameters": contract.model_json_schema(),
                    "strict": False,
                }
            )
        if experiment("fastpath") and self.previous:
            finished = await self.add_requested_blocks()
            if finished is not None:
                finished.tool_trace = self.trace
                return finished
        messages = [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "request_id": str(self.request.request_id),
                        "request": self.request.model_dump(
                            mode="json", exclude={"data_result"}
                        ),
                        "previous_plan": self.previous.model_dump(mode="json")
                        if self.previous
                        else None,
                        "evidence_catalog": self.catalog(),
                        "budget_seconds": self.agent.limits.timeout_seconds,
                    },
                    ensure_ascii=False,
                ),
            }
        ]
        while self.turns < self.agent.limits.max_turns:
            self.context_window.prepare(
                self.agent.model,
                self.agent.prompt,
                messages,
                functions,
                self.checkpoint,
            )
            before = time.perf_counter()
            try:
                turn = await self.agent.model.respond(
                    self.agent.prompt, messages, functions
                )
            except ModelFailure as exc:
                if (
                    not self.previous
                    or exc.code != "MODEL_INCOMPLETE_RESPONSE"
                    or any(t.get("code") == exc.code for t in self.trace)
                ):
                    raise
                # Una respuesta truncada aún no ejecutó herramientas: un solo
                # reintento con el patch mínimo es seguro y queda en la traza.
                self.trace.append(
                    {"tool": "model_response", "status": "retry", "code": exc.code}
                )
                messages.append(
                    {
                        "role": "user",
                        "content": "La respuesta quedó incompleta. Usa update_report y sólo el patch mínimo de los bloques solicitados. No repitas el plan anterior, HTML ni texto analítico.",
                    }
                )
                turn = await self.agent.model.respond(
                    self.agent.prompt, messages, functions
                )
            self.timings["model"] += (time.perf_counter() - before) * 1000
            self.turns += 1
            self.context_window.observe(turn)
            self.tokens += turn.total_tokens
            messages.extend(turn.output)
            calls = [c for c in turn.output if c.get("type") == "function_call"]
            if not calls:
                messages.append(
                    {
                        "role": "user",
                        "content": "Debes llamar a una herramienta real: render_report, request_data o finish_insight_request. No escribas JSON/HTML como texto.",
                    }
                )
                continue
            if len(calls) > 1 and any(
                c.get("name")
                in {
                    "render_report",
                    "render_insight",
                    "update_report",
                    "finish_insight_request",
                }
                for c in calls
            ):
                for c in calls:
                    messages.append(
                        {
                            "type": "function_call_output",
                            "call_id": c["call_id"],
                            "output": '{"error":"TERMINAL_CALL_MUST_BE_SEPARATE"}',
                        }
                    )
                continue
            for call in calls:
                self.calls += 1
                if self.calls > self.agent.limits.max_tool_calls:
                    return self.result("error", issues=["TOOL_BUDGET_EXCEEDED"])
                entry = {
                    "tool": call.get("name")
                    if call.get("name")
                    in {
                        *MODELS,
                        "request_data",
                        "finish_insight_request",
                        "update_report",
                    }
                    else "unknown",
                    "status": "started",
                }
                self.trace.append(entry)
                before_call = time.perf_counter()
                try:
                    if len(call.get("arguments", "")) > 65536:
                        raise ValueError("ARGUMENT_BUDGET")
                    args = json.loads(call["arguments"])
                    output, finished = await self.call(call["name"], args)
                    if call["name"] in {
                        "list_insights",
                        "describe_insight",
                        "validate_report",
                    }:
                        self.observations[
                            json.dumps([call["name"], args], sort_keys=True)
                        ] = {
                            "operation": call["name"],
                            "arguments": args,
                            "result": output,
                        }
                    entry.update(
                        status="error" if output.get("error") else "ok",
                        elapsed_ms=round((time.perf_counter() - before_call) * 1000, 3),
                    )
                    if finished:
                        finished.tool_trace = self.trace
                        return finished
                except ValidationError as exc:
                    output = {
                        "error": "INVALID_TOOL_ARGUMENTS",
                        "fields": [
                            {"path": list(e["loc"]), "type": e["type"]}
                            for e in exc.errors()
                        ],
                    }
                    entry.update(
                        status="error",
                        fields=output["fields"],
                        elapsed_ms=round((time.perf_counter() - before_call) * 1000, 3),
                    )
                except (ValueError, KeyError, TypeError):
                    output = {"error": "INVALID_TOOL_ARGUMENTS"}
                    entry.update(
                        status="error",
                        elapsed_ms=round((time.perf_counter() - before_call) * 1000, 3),
                    )
                messages.append(
                    {
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": json.dumps(output, ensure_ascii=False),
                    }
                )
        return self.result("error", issues=["TURN_BUDGET_EXCEEDED"])

    async def add_requested_blocks(self):
        """EXPERIMENTO LOCAL "fastpath": añadir un gráfico conocido sin modelo.

        Sólo para modificaciones que piden gráficos del catálogo que aún no están
        en la página y cuya evidencia ya existe. Si algo falta o el render no es
        compatible, sigue el flujo normal con el modelo.
        """
        existing = {b.insight_id for b in self.previous.blocks}
        ids = {b.id for b in self.previous.blocks}
        wanted = requested_visuals(self.request.request_text)
        blocks = []
        for recipe, _label in wanted:
            if recipe in existing:
                continue
            sources = set(RECIPE_SOURCES.get(recipe, ()))
            evidence_ids = [
                e.evidence_id for e in self.evidence if e.operation in sources
            ]
            if not evidence_ids:
                # Un gráfico sin datos no impide añadir los que sí los tienen.
                self.trace.append(
                    {
                        "tool": "update_report",
                        "status": "skipped",
                        "deterministic": True,
                        "reason": "MISSING_EVIDENCE",
                        "insight_id": recipe,
                    }
                )
                continue
            block_id = recipe if recipe not in ids else recipe + "_added"
            blocks.append(
                {"id": block_id, "insight_id": recipe, "evidence_ids": evidence_ids}
            )
        if not blocks:
            self.trace.append(
                {
                    "tool": "update_report",
                    "status": "skipped",
                    "deterministic": True,
                    "reason": "NO_NEW_KNOWN_BLOCK",
                    "requested": [recipe for recipe, _ in wanted],
                }
            )
            return None
        entry = {"tool": "update_report", "status": "started", "deterministic": True}
        self.trace.append(entry)
        try:
            output, finished = await self.call("update_report", {"add_blocks": blocks})
        except (ValidationError, ValueError, KeyError, TypeError) as exc:
            entry.update(status="error", reason=type(exc).__name__)
            return None
        entry["status"] = "error" if output.get("error") else "ok"
        if output.get("error"):
            entry["reason"] = output["error"]
        return finished

    async def call(self, name, args):
        if name == "update_report":
            if self.previous is None:
                return {"error": "PREVIOUS_REPORT_REQUIRED"}, None
            args = (
                ReportChanges.model_validate(args)
                .apply(self.previous)
                .model_dump(mode="json")
            )
            name = "render_report"
        if name == "finish_insight_request":
            final = FinishInsight.model_validate(args)
            return {}, self.result(final.status, clarification=final.clarification)
        if name == "request_data":
            requested = RetrieveData.model_validate(args)
            if self.agent.data_client is None:
                return {"error": "DATA_AGENT_NOT_CONFIGURED"}, None
            context = requested.context.model_dump(mode="json")
            for field in ("match_ids", "team_ids", "player_ids", "event_ids"):
                allowed = getattr(self.request.context, field)
                if allowed and not set(getattr(requested.context, field)) <= set(
                    allowed
                ):
                    return {"error": "CONTEXT_SCOPE_MISMATCH"}, None
                if allowed and not context[field]:
                    context[field] = list(allowed)
            if self.request.context.scope is not None:
                context["scope"] = self.request.context.scope.model_dump(mode="json")
            remaining = self.agent.limits.timeout_seconds - (
                time.perf_counter() - self.started
            )
            before = time.perf_counter()
            result = await self.agent.data_client.fetch(
                DataRequest(
                    request_text=requested.request_text,
                    context=context,
                    language=self.request.language,
                    original_request=self.request.original_request,
                ),
                timeout=max(0.01, min(T(40), remaining - 3)),
            )
            self.timings["data_http"] += (time.perf_counter() - before) * 1000
            result = DataResult.model_validate(result)
            self.merge(result)
            return {
                "status": result.status,
                "clarification": result.clarification,
                "issues": [i.model_dump() for i in result.issues],
                "evidence_catalog": self.catalog(),
            }, None
        if name not in MODELS:
            return {"error": "UNKNOWN_TOOL"}, None
        if name in {"render_report", "render_insight", "validate_report"}:
            if name == "render_insight":
                block = RenderInsightRequest.model_validate(args)
                args = {
                    "title": block.title or self.request.request_text[:180],
                    "blocks": [block.model_dump(exclude={"teams"})],
                    "teams": block.teams,
                }
                name = "render_report"
            # El anfitrión preserva el texto original del analista, aunque el
            # modelo intente reemplazarlo dentro del argumento del render.
            args = {
                **args,
                "analyst": self.analyst,
                "language": self.request.language,
            }
            plan = ReportPlan.model_validate(args)
            if (
                not self.previous
                and self.request.required_insights
                and Counter(b.insight_id for b in plan.blocks)
                != Counter(self.request.required_insights)
            ):
                return {
                    "error": "REQUESTED_INSIGHTS_MISMATCH",
                    "required_insights": self.request.required_insights,
                    "actual_insights": [b.insight_id for b in plan.blocks],
                    "repair": "Create exactly the requested recipe counts. A combined chart for both teams is a single block; do not duplicate by team unless requested.",
                }, None
            plan = include_query_pages(plan, self.evidence)
            selected = {key for block in plan.blocks for key in block.evidence_ids}
            if self.request.context.match_ids and any(
                e.evidence_id in selected
                and e.arguments.get("match_id") is not None
                and e.arguments["match_id"] not in self.request.context.match_ids
                for e in self.evidence
            ):
                return {"error": "CONTEXT_SCOPE_MISMATCH"}, None
            args = plan.model_dump(mode="json")
        before = time.perf_counter()
        async with Client(create_server(self.evidence)) as client:
            result = await client.call_tool(name, args)
            if result.is_error:
                return {
                    "error": "MCP_REJECTED_PLAN",
                    "hint": "Revisa IDs, parámetros y requisitos con describe_insight.",
                }, None
            output = result.structured_content
            if name == "render_report":
                if any(
                    b["state"] in {"incompatible", "error"} for b in output["blocks"]
                ):
                    return {
                        "error": "INCOMPATIBLE_BLOCKS",
                        "blocks": output["blocks"],
                    }, None
                html = (
                    (await client.read_resource(output["resource_uri"]))
                    .contents[0]
                    .text
                )
                self.timings["mcp"] += (time.perf_counter() - before) * 1000
                status = (
                    "complete"
                    if not self.data_partial
                    and all(b["state"] == "ready" for b in output["blocks"])
                    else "partial"
                )
                return {}, self.result(
                    status, html=html, plan=plan, blocks=output["blocks"]
                )
        self.timings["mcp"] += (time.perf_counter() - before) * 1000
        return preview(output, list_limit=40), None
