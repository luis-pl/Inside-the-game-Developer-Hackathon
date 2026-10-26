"""Agente de insights: pregunta o intención → informe y respuesta estructurada.

Sin estado: el cliente devuelve `answer.next` en la siguiente petición. El LLM
sólo interpreta preguntas en texto (planificador); con una intención ya formada
no se usa. El resumen es determinista y no hace análisis deportivo (eso es del
analista): dice qué se muestra, qué no y por qué, y si los datos son sintéticos.
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from uuid import uuid4

from pydantic import ValidationError

from inside_game.insights.catalog import RECIPES

from .composer import compose
from .contracts import (
    AskRequest,
    BlockSummary,
    Clarification,
    InsightAnswer,
    Previous,
    ResolvedPlan,
)
from .planner import InsightQuestion, Planner
from .resolver import SNAPSHOT, Resolver

log = logging.getLogger("inside_game.insights_agent")
CODE = re.compile(r"^[A-Z][A-Z0-9_]{2,60}$")


@dataclass(frozen=True)
class AskResult:
    answer: InsightAnswer
    # Aparte de la respuesta: pesa de 1 a 9 MB y no todos los clientes lo quieren.
    report_html: str | None = None
    # Plan del informe para componerlo con las piezas atómicas en otra página.
    report_manifest: dict | None = None


class InsightsAgent:
    def __init__(self, data, *, model=None, profiles=None, timeout_seconds=55):
        self.data = data
        self.planner = Planner(model, data, profiles=profiles) if model else None
        self.resolver = Resolver(data.fetch, profiles=profiles)
        self.timeout_seconds = timeout_seconds

    async def ask(self, request: AskRequest | dict) -> AskResult:
        try:
            request = AskRequest.model_validate(request)
        except ValidationError:
            return error_result(uuid4(), "INVALID_REQUEST", None)
        timings = {}
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self.timeout_seconds):
                result = await self._ask(request, timings)
        except TimeoutError:
            result = error_result(
                request.request_id, "DEADLINE_EXCEEDED", request.previous
            )
        except Exception:
            # Frontera pública: el detalle queda en el log, no en la respuesta.
            log.exception("insights ask failed request=%s", request.request_id)
            result = error_result(
                request.request_id, "INSIGHTS_AGENT_FAILED", request.previous
            )
        timings["total_ms"] = _ms(started)
        result.answer.timings_ms.update(timings)
        return result

    async def _ask(self, request, timings):
        previous = request.previous or Previous()
        intent = request.intent
        if intent is None:
            if self.planner is None:
                return error_result(request.request_id, "MODEL_UNAVAILABLE", previous)
            started = time.perf_counter()
            planned = await self.planner.plan(
                InsightQuestion(
                    request_id=request.request_id,
                    question=request.question,
                    previous_intent=previous.intent,
                    clarification=previous.clarification,
                    clarified_question=previous.question,
                )
            )
            timings["planner_ms"] = _ms(started)
            if planned.status == "clarification":
                clarification = Clarification(
                    question=planned.message, options=planned.options
                )
                return AskResult(
                    InsightAnswer(
                        request_id=request.request_id,
                        kind="clarification",
                        summary=planned.message,
                        clarification=clarification,
                        # Se conserva la pregunta original si ya era una aclaración.
                        next=Previous(
                            intent=previous.intent,
                            clarification=clarification,
                            question=previous.question
                            if previous.clarification
                            else request.question,
                        ),
                    )
                )
            if planned.status == "declined":
                return AskResult(
                    InsightAnswer(
                        request_id=request.request_id,
                        kind="declined",
                        summary=planned.message,
                        next=Previous(intent=previous.intent),
                    )
                )
            if planned.status != "intent":
                return error_result(
                    request.request_id,
                    planned.issues[-1] if planned.issues else "PLANNER_FAILED",
                    previous,
                )
            intent = planned.intent
        started = time.perf_counter()
        try:
            plan = await self.resolver.resolve(intent)
        except ValueError as exc:
            code, cause = resolver_error(exc)
            return error_result(request.request_id, code, previous, cause)
        timings["resolve_ms"] = _ms(started)
        started = time.perf_counter()
        title = report_title(plan)
        composition = await compose(plan, self.data, title=title)
        timings["compose_ms"] = _ms(started)
        answer = InsightAnswer(
            request_id=request.request_id,
            kind="report",
            summary=summarize(plan, composition, title),
            title=title,
            notes=decision_notes(plan, composition),
            intent=plan.intent,
            labels=plan.labels,
            blocks=[
                BlockSummary(
                    id=b.id,
                    insight_id=b.insight_id,
                    title=b.title,
                    state=b.state,
                    warnings=b.warnings,
                    metrics=b.metrics,
                )
                for b in composition.blocks
            ],
            discarded=composition.discarded,
            decisions=plan.decisions,
            has_report=composition.html is not None,
            next=Previous(intent=plan.intent),
        )
        return AskResult(answer, composition.html, composition.manifest)


def _ms(started):
    return round((time.perf_counter() - started) * 1000)


def resolver_error(exc):
    """`CÓDIGO: causa` del resolvedor → (código, causa); nunca texto libre.

    Un ValidationError de pydantic también es ValueError: su mensaje no es un
    código y no debe llegar a la respuesta.
    """
    code, _, cause = str(exc).partition(":")
    cause = cause.strip()
    if not CODE.match(code):
        return "RESOLVE_FAILED", None
    if code == "MATCH_CONTEXT_UNAVAILABLE" and cause in {
        "NOT_FOUND",
        "MATCH_NOT_FOUND",
    }:
        return "MATCH_NOT_FOUND", None
    return code, cause if CODE.match(cause) else None


def error_result(request_id, code, previous, cause=None):
    if code in ERROR_TEXT:
        summary = ERROR_TEXT[code]
    elif code.startswith("MODEL_"):
        summary = "El modelo no pudo interpretar la pregunta: envía una intención estructurada o inténtalo más tarde."
    else:
        summary = "No se pudo preparar el informe."
    return AskResult(
        InsightAnswer(
            request_id=request_id,
            kind="error",
            summary=summary,
            issues=[code] + ([cause] if cause else []),
            next=previous,
        )
    )


ERROR_TEXT = {
    "MODEL_UNAVAILABLE": "No hay modelo para interpretar texto: envía una intención estructurada.",
    "INVALID_REQUEST": "La petición no es válida: envía una pregunta o una intención.",
    "DEADLINE_EXCEEDED": "El informe tardó demasiado y se canceló.",
    "MATCH_CONTEXT_UNAVAILABLE": "No se pudo leer el partido en el agente de datos.",
    "MATCH_NOT_FOUND": "Ese partido no está en el catálogo.",
    "INSIGHTS_AGENT_UNAVAILABLE": "El agente de insights no responde.",
    "INSIGHTS_AGENT_REJECTED": "El agente de insights rechazó la petición.",
    "INSIGHTS_AGENT_FAILED": "El agente de insights falló al preparar el informe.",
    "INVALID_INSIGHTS_RESPONSE": "El agente de insights devolvió una respuesta no válida.",
    "TEAM_NOT_IN_MATCH": "Ese equipo no jugó este partido.",
    "PLAYER_NOT_IN_MATCH": "Ese jugador no figura en este partido.",
}


def clock(ms):
    seconds = ms // 1000
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def report_title(plan: ResolvedPlan):
    intent, labels = plan.intent, plan.labels
    if intent.template_id == "match_overview":
        title = f"Resumen · {labels.match}"
    elif intent.template_id == "player_dossier":
        title = f"Ficha de {labels.player} · {labels.match}"
    elif intent.template_id == "entity_comparison":
        title = f"Comparación · {labels.match}"
    elif intent.template_id == "tactical_episode":
        moment = plan.decisions.get("time_ms")
        period = plan.decisions.get("period")
        at = f" · P{period} {clock(moment)}" if moment is not None else ""
        title = f"Episodio · {labels.focus_team}{at} · {labels.match}"
    else:
        names = [RECIPES[k]["title"] for k in intent.insight_ids]
        topic = " y ".join(names) if len(names) <= 2 else "Informe"
        if intent.team_id:
            rival = (
                labels.away_team
                if labels.focus_team == labels.home_team
                else labels.home_team
            )
            title = f"{topic} · {labels.focus_team} (vs {rival})"
        else:
            title = f"{topic} · {labels.match}"
    if intent.period and intent.template_id != "tactical_episode":
        title += f" · {intent.period}.ª parte"
    return title + (" (SINTÉTICO)" if labels.synthetic else "")


def source_phrase(labels):
    if labels.synthetic:
        return "datos SINTÉTICOS de demostración"
    kind = {
        "real_anonymized": "reales anonimizados",
        "real_pseudonymized": "reales seudonimizados",
    }.get(labels.data_kind, "reales")
    return f"datos {kind} de {labels.provider}" if labels.provider else f"datos {kind}"


def summarize(plan, composition, title):
    """Qué se muestra, qué no y por qué. Sin cifras deportivas ni interpretación."""
    labels = plan.labels
    team_names = {
        plan.home_team_id: labels.home_team,
        plan.away_team_id: labels.away_team,
    }
    lines = [f"{title}. Fuente: {source_phrase(labels)}."]
    if composition.blocks:
        shown = "; ".join(b.title for b in composition.blocks)
        count = len(composition.blocks)
        noun = "pieza" if count == 1 else "piezas"
        lines.append(f"Se muestra{'n' if count != 1 else ''} {count} {noun}: {shown}.")
    else:
        lines.append("No hay piezas que mostrar con estos datos.")
    seen = set()
    for item in composition.discarded:
        name = RECIPES[item.insight_id]["title"]
        if item.team_id in team_names:
            name += f" ({team_names[item.team_id]})"
        if (name, item.reason) in seen:
            continue
        seen.add((name, item.reason))
        lines.append(f"No se muestra {name}: {item.reason}")
    lines += decision_notes(plan, composition)
    return " ".join(lines)


def decision_notes(plan, composition):
    """Lo que el agente decidió sin que el usuario lo dijera: equipo e instante."""
    labels = plan.labels
    team_names = {
        plan.home_team_id: labels.home_team,
        plan.away_team_id: labels.away_team,
    }
    lines = []
    if plan.intent.team_id is None and plan.intent.player_id is None:
        lines.append(f"Equipo protagonista por defecto: {labels.focus_team} (local).")
    if adjusted := plan.decisions.get("team_adjusted_from"):
        requested = team_names.get(adjusted, f"equipo {adjusted}")
        lines.append(
            f"Equipo protagonista ajustado a {labels.focus_team}: el jugador "
            f"pertenece a ese equipo, no a {requested}."
        )
    if any(b.insight_id in SNAPSHOT for b in composition.blocks):
        moment = f"P{plan.decisions['period']} {clock(plan.decisions['time_ms'])}"
        if "instant_adjusted_from_ms" in plan.decisions:
            lines.append(
                f"Instante ajustado a {moment}: era el más cercano con todos los "
                "jugadores posicionados."
            )
        elif why := plan.decisions.get("moment"):
            if "moment_ms" in plan.decisions:
                lines.append(
                    f"Instante analizado: {moment}, el más cercano con todos los "
                    f"jugadores posicionados a {clock(plan.decisions['moment_ms'])} "
                    f"({why})."
                )
            else:
                lines.append(f"Instante analizado: {moment} ({why}).")
        else:
            lines.append(f"Instante analizado: {moment}.")
    return lines
