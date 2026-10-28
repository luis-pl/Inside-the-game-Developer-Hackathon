"""Texto natural -> function calls validadas -> MCP -> evidencia original.

run() usa estado local por solicitud, por lo que una instancia puede atender
varios consumidores sin mezclar conversaciones o evidencias. El modelo propone;
este ejecutor controla herramientas, paginación, presupuestos y finalización.
"""

import asyncio
import hashlib
import json
import logging
import re
import sysconfig
import time
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field, ValidationError

from inside_game.agents.context_window import ContextWindow
from inside_game.agents.contracts import (
    AgentIssue,
    DataRequest,
    DataResult,
    Evidence,
    FinishRequest,
    Message,
)
from inside_game.contracts import ApiResponse
from inside_game.mcp_server import DESCRIPTIONS
from inside_game.providers.models import ModelFailure, ModelProvider
from inside_game.service import OPERATIONS

log = logging.getLogger("inside_game.data_agent")
FINISH = "finish_data_request"
DISCOVER = "describe_data_tools"
DISCOVERY_BASE = {
    "describe_dataset",
    "list_matches",
    "find_entities",
    "get_match_context",
}
TRANSIENT = {"RATE_LIMITED", "BUSY", "API_UNAVAILABLE"}


class DescribeTools(Message):
    tool_names: list[str] = Field(min_length=1, max_length=40)
    full_schema: bool = False


def contextual_schema(name, schema, context):
    """Project fixed filters out when the host supplies validated defaults.

    Discovery can restore the complete schema for explicit refinements.
    """
    schema = json.loads(json.dumps(schema))
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    for field, selected in (
        ("match_id", context.match_ids),
        ("team_id", context.team_ids),
        ("player_id", context.player_ids),
    ):
        if (
            field in properties
            and len(selected) == 1
            and not (name == "get_tracking_window" and field != "match_id")
        ):
            properties.pop(field)
            required.discard(field)
    if (
        "scope" in properties
        and context.scope is not None
        and context.scope.kind == "window"
    ):
        properties.pop("scope")
        required.discard("scope")
    if "sample_step_ms" in properties and context.sample_step_ms is not None:
        properties["sample_step_ms"] = {
            "type": "integer",
            "const": context.sample_step_ms,
            "default": context.sample_step_ms,
            "description": "Omit to inherit the requested sampling interval.",
        }
    schema["required"] = sorted(required)
    return schema


@dataclass(frozen=True)
class AgentLimits:
    max_turns: int = 16
    max_tool_calls: int = 60  # Incluye páginas y reintentos, no sólo decisiones LLM.
    max_pages_per_query: int = 20
    max_evidence_bytes: int = 8 * 1024 * 1024
    max_input_bytes: int = 300 * 1024
    max_tokens: int = (
        160000  # Consumo observado; una respuesta en curso puede excederlo.
    )
    timeout_seconds: float = 240

    def __post_init__(self):
        if any(value <= 0 for value in self.__dict__.values()):
            raise ValueError("Agent limits must be positive")


def load_prompt():
    # Una sola fuente editable en prompts/. El wheel la instala como data-file.
    source = Path(__file__).resolve().parents[3] / "prompts/data_agent.md"
    installed = (
        Path(sysconfig.get_path("data")) / "share/inside-game/prompts/data_agent.md"
    )
    path = source if source.is_file() else installed
    return path.read_text(encoding="utf-8")


def preview(value, depth=0, *, list_limit=8):
    """Acota el contexto LLM; nunca modifica la evidencia entregada al consumidor."""
    if depth > 7:
        return {"preview_omitted": True}
    if isinstance(value, list):
        items = [
            preview(v, depth + 1, list_limit=list_limit) for v in value[:list_limit]
        ]
        return (
            {"items": items, "total_items": len(value), "preview_only": True}
            if len(value) > list_limit
            else items
        )
    if isinstance(value, dict):
        items = {
            k: preview(v, depth + 1, list_limit=list_limit)
            for k, v in list(value.items())[:50]
        }
        return (
            {"items": items, "total_keys": len(value), "preview_only": True}
            if len(value) > 50
            else items
        )
    if isinstance(value, str) and len(value) > 800:
        return value[:800] + " [preview truncated]"
    return value


def allowed_values(error):
    """Schema-authored enum hints only; never echo invalid input or secrets."""
    context = error.get("ctx") or {}
    allowed = context.get("expected_tags") or context.get("expected")
    return {"allowed": str(allowed)[:300]} if allowed else {}


class StopRun(Exception):
    def __init__(self, code):
        self.code = code


class DataAgent:
    def __init__(
        self,
        model: ModelProvider,
        *,
        limits=None,
        prompt=None,
        tool_schema_mode="progressive",
    ):
        if tool_schema_mode not in {"full", "progressive"}:
            raise ValueError("INVALID_TOOL_SCHEMA_MODE")
        self.tool_schema_mode = tool_schema_mode
        self.model = model
        self.limits = limits or AgentLimits()
        self.prompt = prompt if prompt is not None else load_prompt()

    async def run(self, request: DataRequest | dict | str, mcp) -> DataResult:
        if isinstance(request, str):
            request = {"request_text": request}
        request = DataRequest.model_validate(request)
        run = _Run(self, request, mcp)
        try:
            async with asyncio.timeout(self.limits.timeout_seconds):
                return await run.execute()
        except TimeoutError:
            return run.failed("DEADLINE_EXCEEDED")
        except StopRun as exc:
            return run.failed(exc.code)
        except ModelFailure as exc:
            return run.failed(exc.code)
        except Exception:  # noqa: BLE001 - frontera pública; errores SDK pueden incluir secretos.
            # Los errores del transporte/SDK pueden contener cuerpos y headers.
            # El detalle no se registra ni se devuelve al solicitante o al modelo.
            return run.failed("AGENT_EXECUTION_FAILED")


class _Run:
    def __init__(self, agent, request, mcp):
        self.agent, self.request, self.mcp = agent, request, mcp
        self.evidence, self.issues = [], []
        self.calls = self.turns = self.tokens = self.byte_count = 0
        self.cache = {}
        self.incomplete_queries = set()
        self.tools = {}
        self.text_only_replies = 0
        self.context_window = ContextWindow(agent.limits.max_input_bytes)
        self.trace = []
        self.active_tools = set()
        self.full_schemas = set()

    def tool_manifest(self):
        return [
            {"name": name, "description": DESCRIPTIONS[name]} for name in self.tools
        ]

    def result(self, status, *, clarification=None, notes=None, evidence=None):
        return DataResult(
            request_id=self.request.request_id,
            status=status,
            clarification=clarification,
            notes=notes or [],
            evidence=self.evidence if evidence is None else evidence,
            issues=self.issues,
            model=self.agent.model.name,
            tool_calls=self.calls,
            model_turns=self.turns,
            total_tokens=self.tokens,
            context_events=self.context_window.events,
            tool_trace=self.trace,
            prompt_sha256=hashlib.sha256(self.agent.prompt.encode()).hexdigest(),
        )

    def failed(self, code):
        self.issues.append(AgentIssue(code=code))
        return self.result("partial" if self.evidence else "error")

    def checkpoint(self):
        return {
            **self.request.model_dump(mode="json"),
            "completed_queries": [
                {
                    "operation": json.loads(key)[0],
                    "arguments": json.loads(key)[1],
                    **value,
                }
                for key, value in self.cache.items()
            ],
            "incomplete_queries": sorted(self.incomplete_queries),
            "issues": [i.model_dump() for i in self.issues],
            "remaining_tool_calls": self.agent.limits.max_tool_calls - self.calls,
            "tool_catalog": self.tool_manifest(),
            "enabled_tool_schemas": sorted(self.active_tools),
        }

    async def execute(self):
        # Cruce de listas: descubrimiento remoto + registro local cerrado. No se
        # aceptan herramientas nuevas ni schemas alterados por otro servidor.
        discovered = (await self.mcp.list_tools()).tools
        for tool in discovered:
            if (
                tool.name in OPERATIONS
                and tool.input_schema == OPERATIONS[tool.name].model_json_schema()
            ):
                self.tools[tool.name] = tool
        if not self.tools:
            raise StopRun("NO_COMPATIBLE_TOOLS")
        functions = [
            {
                "type": "function",
                "name": t.name,
                "description": DESCRIPTIONS[t.name]
                + " Sólo lectura; conserva la procedencia (sintética o real "
                "anonimizada/seudonimizada), la cobertura y las advertencias.",
                "parameters": t.input_schema,
                "strict": False,
            }
            for t in self.tools.values()
        ]
        functions.append(
            {
                "type": "function",
                "name": FINISH,
                "description": "Finaliza la recuperación seleccionando evidencia original existente.",
                "parameters": FinishRequest.model_json_schema(),
                "strict": True,
            }
        )
        text = self.request.request_text + " " + (self.request.original_request or "")
        self.active_tools = (
            set(self.tools)
            if self.agent.tool_schema_mode == "full"
            else (
                DISCOVERY_BASE
                | {
                    name
                    for name in self.tools
                    if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text)
                }
            )
            & set(self.tools)
        )
        discovery = {
            "type": "function",
            "name": DISCOVER,
            "strict": False,
            "description": "Enable ANY tools in tool_catalog. Selected IDs/windows are applied by the host. Set full_schema=true to expose all original parameters when you need subwindows or other explicit refinements. No data query is executed.",
            "parameters": DescribeTools.model_json_schema(),
        }
        messages = [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        **self.request.model_dump(mode="json"),
                        "tool_catalog": self.tool_manifest(),
                        "tool_schema_mode": self.agent.tool_schema_mode,
                    },
                    ensure_ascii=False,
                ),
            }
        ]
        while self.turns < self.agent.limits.max_turns:
            if self.tokens >= self.agent.limits.max_tokens:
                raise StopRun("TOKEN_BUDGET_EXCEEDED")
            active_functions = [
                f
                for f in functions
                if f["name"] in self.active_tools or f["name"] == FINISH
            ]
            if self.agent.tool_schema_mode == "progressive":
                active_functions = [
                    {
                        **f,
                        "parameters": contextual_schema(
                            f["name"], f["parameters"], self.request.context
                        ),
                    }
                    if f["name"] in self.tools and f["name"] not in self.full_schemas
                    else f
                    for f in active_functions
                ]
                active_functions.append(discovery)
            self.context_window.prepare(
                self.agent.model,
                self.agent.prompt,
                messages,
                active_functions,
                self.checkpoint,
            )
            turn = await self.agent.model.respond(
                self.agent.prompt, messages, active_functions
            )
            self.turns += 1
            self.context_window.observe(turn)
            self.tokens += turn.total_tokens
            messages.extend(turn.output)
            calls = [
                item for item in turn.output if item.get("type") == "function_call"
            ]
            if not calls:
                if self.text_only_replies >= 2:
                    raise StopRun("MODEL_EXPECTED_TOOL_CALL")
                self.text_only_replies += 1
                # Algunos modelos de Foundry sólo admiten tool_choice=auto.
                # Pedir corrección del protocolo, sin interpretar texto libre
                # como datos ni ejecutar llamadas extraídas de ese texto.
                messages.append(
                    {
                        "role": "user",
                        "content": "El ejecutor no entrega texto libre. Si ya recuperaste la evidencia o necesitas aclaración, llama AHORA a finish_data_request con los evidence_ids recibidos. Si falta información, llama a la herramienta necesaria. No escribas la llamada como texto.",
                    }
                )
                continue
            if len(calls) > 8:
                raise StopRun("MODEL_EXPECTED_TOOL_CALL")
            # Finalizar en medio de un lote descartaría las consultas restantes.
            # Devuelve una respuesta por call_id para mantener válido el protocolo.
            if len(calls) > 1 and any(c.get("name") == FINISH for c in calls):
                for call in calls:
                    messages.append(
                        {
                            "type": "function_call_output",
                            "call_id": call["call_id"],
                            "output": json.dumps(
                                {"error": {"code": "FINISH_MUST_BE_SEPARATE"}}
                            ),
                        }
                    )
                continue
            for call in calls:
                try:
                    if len(call.get("arguments", "")) > 65536:
                        raise TypeError
                    args = json.loads(call["arguments"])
                    if not isinstance(args, dict):
                        raise TypeError
                except (ValueError, TypeError, KeyError):
                    output = {"error": {"code": "INVALID_ARGUMENT"}}
                else:
                    if call.get("name") == DISCOVER:
                        try:
                            selection = DescribeTools.model_validate(args)
                            requested = selection.tool_names
                            if not set(requested) <= self.tools.keys():
                                raise ValueError
                            self.active_tools.update(requested)
                            if selection.full_schema:
                                self.full_schemas.update(requested)
                            output = {
                                "enabled_tool_schemas": sorted(self.active_tools),
                                "instruction": "Full schemas are in the next turn's function definitions. Call the needed data tools, then finish separately.",
                            }
                        except (ValidationError, ValueError):
                            output = {
                                "error": {
                                    "code": "UNKNOWN_TOOL_SCHEMA",
                                    "allowed_names": sorted(self.tools),
                                }
                            }
                    elif call.get("name") == FINISH:
                        finished, output = self.finish(args)
                        if finished is not None:
                            self.trace.append({"tool": FINISH, "status": "ok"})
                            finished.tool_trace = list(self.trace)
                            return finished
                    else:
                        output = await self.query(call.get("name"), args)
                self.trace.append(
                    {
                        "tool": call.get("name")
                        if call.get("name") in {*self.tools, FINISH, DISCOVER}
                        else "unknown",
                        "status": "error" if output.get("error") else "ok",
                        "error": output.get("error"),
                    }
                )
                messages.append(
                    {
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": json.dumps(output, ensure_ascii=False),
                    }
                )
        raise StopRun("TURN_BUDGET_EXCEEDED")

    def finish(self, arguments):
        try:
            final = FinishRequest.model_validate(arguments)
        except ValidationError as exc:
            return None, {
                "error": {
                    "code": "INVALID_FINISH_ARGUMENT",
                    "fields": [
                        {
                            "location": list(e["loc"]),
                            "type": e["type"],
                            **allowed_values(e),
                        }
                        for e in exc.errors()
                    ],
                    "repair": {
                        "evidence_ids": [e.evidence_id for e in self.evidence],
                        "clarification": None,
                        "notes": [],
                    },
                    "instruction": "Keep your intended status. evidence_ids and notes must be JSON arrays; notes=[] if none. Never double-encode arrays or write a tool call as text.",
                }
            }
        ids = set(final.evidence_ids)
        available = {e.evidence_id for e in self.evidence}
        if not ids <= available:
            return None, {"error": {"code": "UNKNOWN_EVIDENCE_ID"}}
        if (
            final.status == "needs_clarification"
            and not (final.clarification or "").strip()
        ):
            return None, {"error": {"code": "CLARIFICATION_REQUIRED"}}
        selected = [e for e in self.evidence if e.evidence_id in ids]
        status = final.status
        if status == "complete":
            if not selected:
                return None, {"error": {"code": "EVIDENCE_REQUIRED"}}
            # Un resultado parcial jamás se convierte en completo al omitir la
            # última página: se incluyen todas las páginas de cada query elegida.
            selected_queries = {e.query_id for e in selected}
            # No basta con incluir todas las páginas de UNA consulta: el modelo
            # tampoco puede ocultar otra consulta analítica entera y decir complete.
            omitted_queries = {
                e.query_id
                for e in self.evidence
                if e.operation
                not in {"describe_dataset", "find_entities", "list_matches"}
                and e.query_id not in selected_queries
            }
            if omitted_queries:
                return None, {
                    "error": {
                        "code": "OMITTED_QUERY_EVIDENCE",
                        "evidence_ids": [
                            e.evidence_id
                            for e in self.evidence
                            if e.query_id in omitted_queries
                        ],
                    }
                }
            all_pages = {
                e.evidence_id for e in self.evidence if e.query_id in selected_queries
            }
            if ids != all_pages or self.incomplete_queries:
                status = "partial"
                self.issues.append(AgentIssue(code="INCOMPLETE_EVIDENCE_SELECTION"))
        return self.result(
            status,
            clarification=final.clarification,
            notes=final.notes,
            evidence=selected,
        ), None

    async def query(self, name, arguments):
        if name not in self.tools:
            return {"error": {"code": "UNREGISTERED_OPERATION"}}
        if arguments.get("cursor") is not None:
            return {"error": {"code": "CURSOR_MANAGED_BY_AGENT"}}
        # Preserve the explicit handoff even if the model omits a filter.
        # Discovery remains unfiltered; only fields in the approved schema can
        # be supplied. Multiple selected entities are never reduced to the first.
        arguments = dict(arguments)
        fields = OPERATIONS[name].model_fields
        sampling = self.request.context.sample_step_ms
        if name == "get_tracking_window" and sampling is not None:
            if (
                arguments.get("sample_step_ms") not in (None, sampling)
                or arguments.get("stride_s", 1) != 1
            ):
                return {"error": {"code": "CONTEXT_RESOLUTION_MISMATCH"}}
            arguments["sample_step_ms"] = sampling
            arguments["stride_s"] = 1
        if name not in {"describe_dataset", "find_entities", "list_matches"}:
            for field, selected in (
                ("match_id", self.request.context.match_ids),
                ("team_id", self.request.context.team_ids),
                ("player_id", self.request.context.player_ids),
            ):
                if field not in fields or not selected:
                    continue
                if (
                    type(arguments.get(field)) is int
                    and arguments[field] not in selected
                ):
                    return {
                        "error": {
                            "code": "CONTEXT_SCOPE_MISMATCH",
                            "field": field,
                            "allowed": selected,
                            "repair": f"Omit {field} to inherit the selection when unique.",
                        }
                    }
                if (
                    arguments.get(field) is None
                    and len(selected) == 1
                    and not (
                        name == "get_tracking_window"
                        and field in {"team_id", "player_id"}
                    )
                ):
                    arguments[field] = selected[0]
            if "scope" in fields and self.request.context.scope is not None:
                selected_scope = self.request.context.scope.model_dump(mode="json")
                if (
                    arguments.get("time_ms") is not None
                    or arguments.get("event_id") is not None
                ):
                    # Spatial snapshots and interval queries are mutually
                    # exclusive at the API. A point is a valid narrowing of the
                    # selected window; do not inject that window as a second
                    # temporal selector.
                    if (
                        arguments.get("time_ms") is not None
                        and "period" in fields
                        and arguments.get("period") is None
                        and selected_scope.get("period") is not None
                    ):
                        arguments["period"] = selected_scope["period"]
                else:
                    arguments.setdefault("scope", selected_scope)
        try:
            request = OPERATIONS[name].model_validate(arguments)
        except ValidationError as exc:
            return {
                "error": {
                    "code": "INVALID_ARGUMENT",
                    "fields": [
                        {
                            "location": list(e["loc"]),
                            "type": e["type"],
                            **allowed_values(e),
                        }
                        for e in exc.errors()
                    ],
                    "repair": "Omit match_id, team_id, player_id or scope when their exact values are already selected in context; the host inherits them. All IDs/times are JSON integers. A window is flat {kind,period,start_ms,end_ms}, never {window:{...}}.",
                }
            }
        args = request.model_dump(mode="json")
        if self.request.context.scope is not None and args.get("time_ms") is not None:
            selected = self.request.context.scope.model_dump(mode="json")
            if (
                "scope" in args
                and args["scope"].get("kind") != "match"
                and args.get("period") is not None
            ):
                return {
                    "error": {
                        "code": "SNAPSHOT_OR_SCOPE_REQUIRED",
                        "repair": {"scope": {"kind": "match"}},
                        "instruction": "For a point use period + time_ms and default match scope; for an interval use scope window and omit period/time_ms.",
                    }
                }
            if selected["kind"] in {"period", "window"} and (
                args.get("period", args.get("scope", {}).get("period"))
                != selected["period"]
                or (
                    selected["kind"] == "window"
                    and not selected["start_ms"] <= args["time_ms"] < selected["end_ms"]
                )
            ):
                return {"error": {"code": "CONTEXT_SCOPE_MISMATCH", "field": "time_ms"}}
        elif (
            "scope" in args
            and self.request.context.scope is not None
            and args.get("event_id") is None
        ):
            selected = self.request.context.scope.model_dump(mode="json")
            actual = args["scope"]
            # Narrowing is allowed (including splitting a long window), widening
            # or crossing a period is not. Match scope imposes no time filter.
            if selected["kind"] in {"period", "window"} and (
                actual.get("kind") not in {"period", "window"}
                or actual.get("period") != selected["period"]
                or (
                    selected["kind"] == "window"
                    and (
                        actual.get("kind") != "window"
                        or actual["start_ms"] < selected["start_ms"]
                        or actual["end_ms"] > selected["end_ms"]
                    )
                )
            ):
                return {"error": {"code": "CONTEXT_SCOPE_MISMATCH", "field": "scope"}}
        key = json.dumps([name, args], sort_keys=True)
        if key in self.cache:
            return self.cache[key]
        query_id = f"q{len(self.cache) + 1}"
        records = []
        seen_cursors = set()
        pages = 0
        while True:
            payload, error = await self.invoke(name, args)
            if error:
                self.issues.append(AgentIssue(code=error, operation=name))
                if error in {"UNAUTHORIZED", "FORBIDDEN"}:
                    raise StopRun(error)
                # Igual que la validación local: un argumento rechazado ANTES
                # de recuperar páginas puede corregirse con otra consulta.
                # Fallar tras una página sí deja evidencia incompleta.
                if error != "INVALID_ARGUMENT" or pages:
                    self.incomplete_queries.add(query_id)
                records.append({"error": {"code": error}})
                break
            # Valida identidad y procedencia; no confiar en texto de herramientas.
            try:
                response = ApiResponse.model_validate(payload)
                if (
                    response.operation_id != name
                    or type(response.provenance.get("is_synthetic")) is not bool
                ):
                    raise ValueError
            except (ValidationError, ValueError):
                raise StopRun("INVALID_MCP_RESPONSE") from None
            size = len(response.model_dump_json().encode())
            if self.byte_count + size > self.agent.limits.max_evidence_bytes:
                self.incomplete_queries.add(query_id)
                raise StopRun("EVIDENCE_BUDGET_EXCEEDED")
            self.byte_count += size
            evidence = Evidence(
                evidence_id=f"e{len(self.evidence) + 1}",
                query_id=query_id,
                operation=name,
                arguments=dict(args),
                response=response,
            )
            self.evidence.append(evidence)
            records.append(
                {
                    "evidence_id": evidence.evidence_id,
                    # Catálogos pequeños completos: mostrar sólo las ocho primeras
                    # filas ocultaba todos los partidos reales tras los sintéticos.
                    "response_preview": preview(
                        response.model_dump(mode="json"),
                        list_limit=200
                        if name in {"list_matches", "find_entities"}
                        else 8,
                    ),
                }
            )
            pages += 1
            cursor = response.pagination.get("next_cursor")
            if not cursor:
                break
            if (
                not isinstance(cursor, str)
                or "cursor" not in OPERATIONS[name].model_fields
                or cursor in seen_cursors
            ):
                raise StopRun("INVALID_PAGINATION")
            if pages >= self.agent.limits.max_pages_per_query:
                self.incomplete_queries.add(query_id)
                self.issues.append(
                    AgentIssue(code="PAGE_BUDGET_EXCEEDED", operation=name)
                )
                records.append({"error": {"code": "PAGE_BUDGET_EXCEEDED"}})
                break
            seen_cursors.add(cursor)
            args = {**args, "cursor": cursor}
            # Cursor opaco: sólo se sustituye ese campo; los demás filtros quedan iguales.
            OPERATIONS[name].model_validate(args)
        result = {
            "query_id": query_id,
            "pages": records,
            "complete": query_id not in self.incomplete_queries
            and not any("error" in record for record in records),
        }
        self.cache[key] = result
        return result

    async def invoke(self, name, args):
        for attempt in range(2):
            if self.calls >= self.agent.limits.max_tool_calls:
                raise StopRun("TOOL_BUDGET_EXCEEDED")
            self.calls += 1
            started = time.monotonic()
            result = await self.mcp.call_tool(name, args)
            log.info(
                "data_tool request=%s operation=%s call=%s duration_ms=%s error=%s",
                self.request.request_id,
                name,
                self.calls,
                int((time.monotonic() - started) * 1000),
                result.is_error,
            )
            if not result.is_error:
                return result.structured_content, None
            try:
                code = json.loads(result.content[0].text)["error"]["code"]
            except (ValueError, KeyError, IndexError, AttributeError, TypeError):
                return None, "INVALID_MCP_RESPONSE"
            if code in TRANSIENT and attempt == 0:
                await asyncio.sleep(1)
                continue
            # Sólo códigos conocidos, nunca mensajes externos que pudieran contener secretos.
            known = TRANSIENT | {
                "UNAUTHORIZED",
                "FORBIDDEN",
                "NOT_FOUND",
                "INVALID_ARGUMENT",
                "RESPONSE_TOO_LARGE",
                "ENTITY_NOT_IN_MATCH",
                "INVALID_API_RESPONSE",
            }
            return None, code if code in known else "MCP_TOOL_FAILED"
        return None, "MCP_TOOL_FAILED"
