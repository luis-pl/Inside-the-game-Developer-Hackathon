"""Data HTTP -> Insights HTTP/MCP -> texto deportivo con hechos referenciados."""

import asyncio
import hashlib
import json
import re
import sysconfig
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from inside_game.agents.analyst_contracts import (
    AnalysisRequest,
    AnalysisResult,
    EarlyAnalysis,
    FinishAnalysis,
    VisualRequest,
)
from inside_game.agents.analyst_facts import (
    TOKEN,
    evidence_facts,
    reference_line,
    render_statement,
    source_key,
    visual_facts,
)
from inside_game.agents.contracts import DataRequest, DataResult
from inside_game.agents.insight_contracts import InsightRequest, RetrieveData
from inside_game.providers.models import ModelFailure


def load_prompt():
    local = Path(__file__).resolve().parents[3] / "prompts/sports_analyst.md"
    installed = (
        Path(sysconfig.get_path("data")) / "share/inside-game/prompts/sports_analyst.md"
    )
    return (local if local.is_file() else installed).read_text(encoding="utf-8")


@dataclass(frozen=True)
class AnalystLimits:
    timeout_seconds: float = 45
    max_turns: int = 8
    max_calls: int = 10
    max_data_requests: int = 2
    max_visual_requests: int = 2
    max_facts: int = 220
    max_input_bytes: int = 220000

    def __post_init__(self):
        if any(v <= 0 for v in self.__dict__.values()):
            raise ValueError("INVALID_ANALYST_LIMITS")


class GroundingError(ValueError):
    def __init__(self, fields):
        self.fields = fields
        super().__init__("INVALID_ANALYSIS_FACTS")


def normalize_finish_arguments(raw):
    """Compatibilidad con doble codificación JSON de algunos tool callers.

    Sólo campos del contrato de finalización; no se corrigen cifras, IDs de
    hechos ni argumentos de consultas. No se ejecuta código ni JSON truncado.
    """
    args = json.loads(raw)
    changed = []
    if not isinstance(args, dict):
        return args, changed
    for key in ("status", "sections", "limitations", "title", "clarification"):
        value = args.get(key)
        if not isinstance(value, str) or not value.lstrip().startswith(("[", "{", '"')):
            continue
        try:
            decoded, end = json.JSONDecoder().raw_decode(value.strip())
            if value.strip()[end:].strip() not in ("", ","):
                continue
            expected = list if key in ("sections", "limitations") else str
            if isinstance(decoded, expected):
                args[key] = decoded
                changed.append(key)
        except ValueError:
            pass
    return args, changed


class SportsAnalyst:
    def __init__(
        self, model, *, data_client=None, insights_client=None, prompt=None, limits=None
    ):
        self.model, self.data_client, self.insights_client = (
            model,
            data_client,
            insights_client,
        )
        self.prompt = load_prompt() if prompt is None else prompt
        self.limits = limits or AnalystLimits()

    async def run(self, request):
        request = AnalysisRequest.model_validate(request)
        state = _Run(self, request)
        try:
            async with asyncio.timeout(self.limits.timeout_seconds):
                return await state.execute()
        except TimeoutError:
            return state.result("error", issues=["DEADLINE_EXCEEDED"])
        except ModelFailure as exc:
            return state.result("error", issues=[exc.code])
        except (ValidationError, ValueError):
            return state.result("error", issues=["INVALID_ANALYSIS_DATA"])
        except Exception:  # noqa: BLE001 - no exponer respuestas SDK ni cabeceras.
            return state.result("error", issues=["ANALYST_EXECUTION_FAILED"])


class _Run:
    def __init__(self, agent, request):
        self.agent, self.request = agent, request
        self.started = time.perf_counter()
        self.evidence = []
        self.facts = []
        self.trace = []
        self.data_ids = []
        self.turns = self.tokens = self.fetches = self.previews = 0
        self.partial = False
        self.visual = None
        self.reviewed = False
        self.visual_aliases = {}

    def remaining(self):
        return max(
            0.01,
            self.agent.limits.timeout_seconds - (time.perf_counter() - self.started),
        )

    def merge(self, result):
        self.partial |= result.status != "complete"
        self.data_ids.append(result.request_id)
        for original in result.evidence:
            match = original.arguments.get("match_id")
            if (
                self.request.context.match_ids
                and match is not None
                and match not in self.request.context.match_ids
            ):
                raise ValueError("EVIDENCE_MATCH_MISMATCH")
            if any(source_key(e) == source_key(original) for e in self.evidence):
                continue
            item = original.model_copy(deep=True)
            if any(e.evidence_id == item.evidence_id for e in self.evidence):
                item.evidence_id = f"data-{result.request_id.hex}-{item.evidence_id}"
            self.evidence.append(item)
        if (
            len(self.evidence) > 100
            or sum(len(e.model_dump_json().encode()) for e in self.evidence)
            > 8 * 1024 * 1024
        ):
            raise ValueError("EVIDENCE_BUDGET_EXCEEDED")
        self.facts = evidence_facts(self.evidence)
        self.reviewed = False
        self.visual = None
        self.visual_aliases = {}
        if len(self.facts) > self.agent.limits.max_facts:
            raise ValueError("FACT_BUDGET_EXCEEDED")

    def result(self, status, **kwargs):
        return AnalysisResult(
            request_id=self.request.request_id,
            status=status,
            model=self.agent.model.name,
            prompt_sha256=hashlib.sha256(self.agent.prompt.encode()).hexdigest(),
            elapsed_ms=round((time.perf_counter() - self.started) * 1000, 3),
            model_turns=self.turns,
            total_tokens=self.tokens,
            tool_trace=self.trace,
            data_request_ids=self.data_ids,
            visual_report=self.visual,
            evidence=self.evidence,
            context=self.request.context,
            visual_evidence_aliases=self.visual_aliases,
            **kwargs,
        )

    def catalog(self):
        scopes = {}
        facts = []
        for fact in self.facts:
            canonical = json.dumps(fact.scope, sort_keys=True)
            if canonical not in scopes:
                scopes[canonical] = (f"s{len(scopes) + 1}", fact.scope)
            facts.append(
                {
                    **fact.model_dump(mode="json", exclude={"scope", "provenance"}),
                    "scope_id": scopes[canonical][0],
                }
            )
        return {
            "scope_catalog": {
                identifier: scope for identifier, scope in scopes.values()
            },
            "method_notes": [
                {
                    "evidence_id": e.evidence_id,
                    "operation": e.operation,
                    "notes": [
                        s.get("result", {}).get("interpretation")
                        for s in e.response.data.get("samples", [])
                        if s.get("result", {}).get("interpretation")
                    ],
                }
                for e in self.evidence
            ],
            "facts": facts,
            "evidence_catalog": [
                {
                    "evidence_id": e.evidence_id,
                    "operation": e.operation,
                    "arguments": e.arguments,
                    "scope": e.response.scope,
                    "provenance": e.response.provenance,
                    "coverage": e.response.coverage,
                    "warnings": e.response.warnings,
                }
                for e in self.evidence
            ],
        }

    async def execute(self):
        if self.request.data_result:
            self.merge(self.request.data_result)
        contracts = {
            "request_data": (
                RetrieveData,
                "Solicita evidencia original a Data por HTTP. Agrupa consultas; conserva contexto. Topología: get_team_shape, get_proximity_connectivity, get_space_coverage, get_persistent_structure, get_node_removal_robustness, con instante/ventana explícitos.",
            ),
            "request_insights": (
                VisualRequest,
                "Pide gráficos a Insights usando sólo evidencia suministrada. Devuelve hechos del renderer y estados; revísalos antes de redactar.",
            ),
            "finish_analysis": (
                FinishAnalysis,
                "Entrega texto por secciones con fact_ids existentes. Las cifras se insertan como {{f-...}}. También permite pedir aclaración o explicar lo no disponible.",
            ),
        }
        tools = [
            {
                "type": "function",
                "name": name,
                "description": description,
                "parameters": model.model_json_schema(),
                "strict": False,
            }
            for name, (model, description) in contracts.items()
        ]
        messages = [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "request_id": str(self.request.request_id),
                        "request": self.request.model_dump(
                            mode="json", exclude={"data_result"}
                        ),
                        **self.catalog(),
                    },
                    ensure_ascii=False,
                ),
            }
        ]
        for _ in range(self.agent.limits.max_turns):
            if (
                len(json.dumps([self.agent.prompt, messages, tools]).encode())
                > self.agent.limits.max_input_bytes
            ):
                return self.result("error", issues=["CONTEXT_BUDGET_EXCEEDED"])
            active_tools = tools
            if self.request.review_visuals and not self.reviewed:
                active_tools = [
                    {
                        **tool,
                        "parameters": EarlyAnalysis.model_json_schema(),
                        "description": "Antes de revisar Insights sólo puedes pedir aclaración o declarar unsupported. Para redactar primero llama a request_insights.",
                    }
                    if tool["name"] == "finish_analysis"
                    else tool
                    for tool in tools
                ]
            turn = await self.agent.model.respond(
                self.agent.prompt, messages, active_tools
            )
            self.turns += 1
            self.tokens += turn.total_tokens
            messages.extend(turn.output)
            calls = [c for c in turn.output if c.get("type") == "function_call"]
            if not calls:
                messages.append(
                    {
                        "role": "user",
                        "content": "Usa una herramienta real. Para terminar llama a finish_analysis; no escribas texto fuera del contrato.",
                    }
                )
                continue
            for call in calls:
                if len(self.trace) >= self.agent.limits.max_calls:
                    return self.result("error", issues=["TOOL_BUDGET_EXCEEDED"])
                name = call.get("name")
                entry = {
                    "tool": name if name in contracts else "unknown",
                    "status": "started",
                }
                self.trace.append(entry)
                started = time.perf_counter()
                try:
                    if name not in contracts or len(call.get("arguments", "")) > 24000:
                        raise ValueError("INVALID_TOOL_CALL")
                    if name == "finish_analysis":
                        normalized, changed = normalize_finish_arguments(
                            call["arguments"]
                        )
                        entry["json_normalized_fields"] = changed
                        args = FinishAnalysis.model_validate(normalized)
                    else:
                        args = contracts[name][0].model_validate_json(call["arguments"])
                    if len(calls) > 1 and name == "finish_analysis":
                        raise ValueError("FINISH_MUST_BE_SEPARATE")
                    if name == "finish_analysis":
                        result = self.finish(args)
                        entry.update(
                            status="ok",
                            elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
                        )
                        return result.model_copy(
                            update={"tool_trace": self.trace}, deep=True
                        )
                    output = await self.query(name, args)
                    entry["status"] = "ok"
                except GroundingError as exc:
                    output = {
                        "error": "INVALID_ANALYSIS_FACTS",
                        "fields": exc.fields,
                        "repair": "Corrige TODAS las afirmaciones indicadas. Sustituye cada cifra por un placeholder real y cita su ID. Escribe primer/segundo tiempo en lugar de P1/P2. Mueve advertencias generales a limitations.",
                    }
                    entry["status"] = "error"
                except ValidationError as exc:
                    output = {
                        "error": "INVALID_ARGUMENT",
                        "fields": [
                            {"path": list(e["loc"]), "type": e["type"]}
                            for e in exc.errors()
                        ],
                    }
                    entry["status"] = "error"
                except ModelFailure as exc:
                    entry.update(
                        status="error",
                        error=exc.code,
                        elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
                    )
                    raise
                except asyncio.CancelledError:
                    entry.update(
                        status="error",
                        error="DEADLINE_EXCEEDED",
                        elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
                    )
                    raise
                except ValueError as exc:
                    code = str(exc)
                    allowed = {
                        "INVALID_TOOL_CALL",
                        "FINISH_MUST_BE_SEPARATE",
                        "DATA_REQUIRED",
                        "DATA_BUDGET_EXCEEDED",
                        "INSIGHTS_BUDGET_EXCEEDED",
                        "FACT_BUDGET_EXCEEDED",
                        "VISUAL_REVIEW_REQUIRED",
                        "UNKNOWN_FACT_REFERENCE",
                        "PLACEHOLDER_REQUIRES_CITATION",
                        "USE_FACT_PLACEHOLDERS_FOR_NUMBERS",
                        "UNTRUSTED_VISUAL_EVIDENCE",
                        "VISUAL_WITHOUT_EVIDENCE",
                        "ANALYSIS_TOO_LONG",
                        "ANALYSIS_REQUIRED",
                    }
                    output = {
                        "error": code if code in allowed else "INVALID_ANALYSIS_DATA"
                    }
                    entry["status"] = "error"
                entry["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
                entry["error"] = output.get("error")
                messages.append(
                    {
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": json.dumps(output, ensure_ascii=False),
                    }
                )
        return self.result("error", issues=["TURN_BUDGET_EXCEEDED"])

    async def query(self, name, args):
        if name == "request_data":
            if (
                not self.agent.data_client
                or self.fetches >= self.agent.limits.max_data_requests
            ):
                raise ValueError("DATA_BUDGET_EXCEEDED")
            self.fetches += 1
            context = self.request.context.model_copy(deep=True)
            for key, value in args.context.model_dump(exclude_unset=True).items():
                existing = getattr(context, key)
                if existing and value != existing:
                    raise ValueError("INVALID_ANALYSIS_DATA")
                setattr(context, key, value)
            result = await self.agent.data_client.fetch(
                DataRequest(request_text=args.request_text, context=context),
                timeout=min(40, self.remaining()),
            )
            self.merge(result)
            return {
                "data_status": result.status,
                "clarification": result.clarification,
                "issues": [i.model_dump() for i in result.issues],
                **self.catalog(),
            }
        if not self.evidence:
            raise ValueError("DATA_REQUIRED")
        if (
            not self.agent.insights_client
            or self.previews >= self.agent.limits.max_visual_requests
        ):
            raise ValueError("INSIGHTS_BUDGET_EXCEEDED")
        self.previews += 1
        result, payload = await self.agent.insights_client.preview(
            InsightRequest(
                request_text=args.request_text
                + " Usa exclusivamente la evidencia suministrada; no pidas nuevos datos ni añadas análisis narrativo.",
                context=self.request.context,
                data_result=DataResult(
                    request_id=uuid4(),
                    status="partial" if self.partial else "complete",
                    model="original-data-handoff",
                    evidence=self.evidence,
                ),
            ),
            timeout=min(35, self.remaining()),
        )
        self.visual = result
        self.reviewed = True
        if payload:
            hashes = {
                hashlib.sha256(source_key(e).encode()).hexdigest(): e.evidence_id
                for e in self.evidence
            }
            self.visual_aliases = {
                hashes[item["source_sha256"]]: item["evidence_id"]
                for item in payload.get("evidence_catalog", [])
                if item.get("source_sha256") in hashes
            }
            self.facts = list(
                {
                    f.id: f
                    for f in [*self.facts, *visual_facts(payload, self.evidence)]
                }.values()
            )
        self.partial |= result.status != "complete"
        if len(self.facts) > self.agent.limits.max_facts:
            raise ValueError("FACT_BUDGET_EXCEEDED")
        return {
            "report_id": str(result.report_id),
            "blocks": result.blocks,
            "issues": result.issues,
            **self.catalog(),
        }

    def finish(self, args):
        if args.status in {"needs_clarification", "unsupported"}:
            if not args.clarification:
                raise ValueError("ANALYSIS_REQUIRED")
            return self.result(args.status, clarification=args.clarification)
        if not args.sections or not self.facts:
            raise ValueError("ANALYSIS_REQUIRED")
        if self.request.review_visuals and not self.reviewed:
            raise ValueError("VISUAL_REVIEW_REQUIRED")
        fields = []
        known = {f.id for f in self.facts}
        for si, section in enumerate(args.sections):
            for pi, item in enumerate(section.statements):
                # Referenciar un placeholder conocido ya identifica su fuente;
                # añadir la cita omitida no crea hechos ni cambia sus valores.
                item.fact_ids = list(
                    dict.fromkeys(
                        [
                            *item.fact_ids,
                            *[t for t in TOKEN.findall(item.text) if t in known],
                        ]
                    )
                )
                try:
                    render_statement(item, self.facts)
                except ValueError as exc:
                    fields.append(
                        {
                            "path": ["sections", si, "statements", pi],
                            "code": str(exc),
                            "literal_numbers": re.findall(
                                r"\d+(?:[.,]\d+)?%?", TOKEN.sub("", item.text)
                            ),
                            "unknown_fact_ids": [
                                t
                                for t in [*item.fact_ids, *TOKEN.findall(item.text)]
                                if t not in known
                            ],
                        }
                    )
        if fields:
            raise GroundingError(fields)
        used = []
        sections = []
        parts = [args.title]
        warnings = list(
            dict.fromkeys(w for e in self.evidence for w in e.response.warnings)
        )
        analytical = [
            e
            for e in self.evidence
            if e.operation not in {"list_matches", "find_entities", "describe_dataset"}
        ]
        kinds = {
            e.response.provenance.get("is_synthetic")
            for e in analytical or self.evidence
        }
        parts.append(
            "Provenance: "
            + (
                "synthetic demonstration data."
                if kinds == {True}
                else "recorded sources; check coverage."
                if kinds == {False}
                else "sources with different provenance; not automatically comparable."
            )
        )
        for section in args.sections:
            statements = []
            parts.append("\n" + section.heading)
            for item in section.statements:
                value = render_statement(item, self.facts)
                for key in item.fact_ids:
                    if key not in used:
                        used.append(key)
                citations = ", ".join(str(used.index(key) + 1) for key in item.fact_ids)
                # El tipo de afirmación permanece en el contrato y la trazabilidad.
                # La prosa del lector conserva las citas sin repetir etiquetas.
                parts.append(f"{value} [{citations}]")
                statements.append(item.model_copy(update={"text": value}))
            sections.append(section.model_copy(update={"statements": statements}))
        limits = list(dict.fromkeys([*args.limitations, *warnings]))
        if any(f.scope.get("exhaustive") is False for f in self.facts):
            limits.append(
                "Table readings use the first ten rows in source order; they do not represent every entity."
            )
        if self.visual and self.visual.status != "complete":
            limits.append(
                "Visual review was incomplete; check the status and limitations of each block."
            )
        parts.append("\nScope and limitations\n" + "\n".join(limits))
        cited = [next(f for f in self.facts if f.id == key) for key in used]
        parts.append(
            "\nReferences\n"
            + "\n".join(reference_line(i + 1, f) for i, f in enumerate(cited))
        )
        text = "\n".join(parts)
        if len(text) > 16000:
            raise ValueError("ANALYSIS_TOO_LONG")
        return self.result(
            "partial"
            if self.partial
            or args.status == "partial"
            or any(f.scope.get("exhaustive") is False for f in self.facts)
            else "complete",
            text=text,
            sections=sections,
            facts=cited,
            limitations=limits,
        )
