"""Plan resuelto → evidencia → MCP de insights → HTML, sin LLM.

El guardián retira antes de mostrar los bloques que confundirían al usuario:
sin evidencia, incompatibles, con error, sin datos o sólo con ceros. Cada
retirada conserva su motivo. Las métricas por bloque se calculan localmente con
`compile_report` porque el MCP de insights todavía no las expone; las necesitan
el guardián y quien narre (analista o LLM). Se entregan con claves estables: sin
el ID de consulta, que cambia entre llamadas y transportes.
"""

from mcp import Client

from inside_game.agents.contracts import Message
from inside_game.insights.mcp_server import create_server
from inside_game.insights.pages import compile_report

from .contracts import Discarded, ResolvedPlan
from .profiles import zero_only

TEAM_COLORS = ("#2463bc", "#bf402e")
HIDDEN_STATES = {"unavailable", "incompatible", "error", "empty_with_coverage"}


class ShownBlock(Message):
    id: str
    insight_id: str
    title: str
    state: str
    warnings: list[str]
    metrics: dict
    evidence_ids: list[str]


class Composition(Message):
    plan: ResolvedPlan
    title: str
    html: str | None
    # El plan validado (bloques, equipos y evidencia): permite componer la misma
    # página con las piezas atómicas dentro de otra aplicación (`report_parts`).
    manifest: dict | None = None
    blocks: list[ShownBlock]
    discarded: list[Discarded]
    api_errors: dict
    evidence_count: int


def _counts(block):
    fields = ("points", "vectors", "series", "rows", "polygons", "frames")
    return {f: len(getattr(block, f)) for f in fields if getattr(block, f)}


def stable_metrics(metrics, evidence):
    """`q12.tackles_won` → `tackles_won`; si dos consultas chocan, `operación.clave`.

    Los adaptadores prefijan los resúmenes con el ID de consulta, que el cliente
    A2A renombra en cada mensaje: sin esto la misma métrica cambia de nombre.
    """
    operations = {e["query_id"]: e["operation"] for e in evidence}
    split = {}
    for key, value in metrics.items():
        query, dot, rest = key.partition(".")
        if dot and query in operations:
            split[key] = (rest, operations[query], value)
        else:
            split[key] = (key, None, value)
    names = [name for name, _, _ in split.values()]
    stable = {}
    for original, (name, operation, value) in split.items():
        key = (
            name
            if names.count(name) == 1 or operation is None
            else f"{operation}.{name}"
        )
        # Dos consultas de la misma operación: se conserva la clave original
        # antes que perder una métrica en silencio.
        stable[original if key in stable else key] = value
    return stable


ERROR_TEXT = {
    "SOURCE_FIELD_UNAVAILABLE": "la fuente no anota los datos que necesita esta pieza",
    "INSUFFICIENT_COVERAGE": "no hay datos de seguimiento suficientes en ese tramo",
    "ENTITY_NOT_IN_MATCH": "el equipo o jugador no participó en este partido",
    "WINDOW_TOO_LARGE": "el tramo pedido es demasiado largo",
    "RATE_LIMITED": "se alcanzó el límite de consultas; reintenta en un minuto",
    "API_UNAVAILABLE": "la API de datos no respondió",
    "INVALID_ARGUMENT": "la fuente rechazó los parámetros de la consulta",
}


def _query_failure(errors):
    """Motivo legible; conserva el código para quien depure."""
    if not errors:
        return "La consulta de datos falló: sin evidencia"
    return "La consulta de datos falló: " + "; ".join(
        f"{ERROR_TEXT[e]} ({e})" if e in ERROR_TEXT else e for e in errors
    )


def _reason(block):
    own = [w for w in block.warnings if not w.startswith(("Synthetic", "Real "))]
    return " ".join(own[:2]) or f"Estado {block.state}."


async def compose(plan: ResolvedPlan, data, *, title: str) -> Composition:
    results = await data.run(plan.queries)
    discarded = list(plan.discarded)
    api_errors = {k: e for k, (_, e) in results.items() if e}
    candidates = []
    for block in plan.blocks:
        errors = [results[k][1] for k in block.query_keys if results[k][1]]
        ids = list(dict.fromkeys(i for k in block.query_keys for i in results[k][0]))
        if errors or not ids:
            discarded.append(
                Discarded(
                    insight_id=block.insight_id,
                    team_id=block.parameters.get("team_id"),
                    reason=_query_failure(errors),
                )
            )
            continue
        candidates.append(
            {
                "id": block.id,
                "insight_id": block.insight_id,
                "title": block.title,
                "evidence_ids": ids,
                "parameters": block.parameters,
            }
        )

    shown = []
    if candidates:
        evidence = _evidence(data, candidates)
        _, compiled = compile_report(
            {
                "blocks": candidates,
                "evidence": evidence,
                "zero_only_insights": plan.zero_only_insights,
                "unannotated_metrics": plan.unannotated_metrics,
            }
        )
        # Con perfil medido, las acciones que la fuente no anota ya se descartaron:
        # un cero restante es real (p. ej. un medio sin tiros). Sin perfil, no se sabe.
        measured = plan.profile_measured
        kept = []
        for spec, block in zip(candidates, compiled, strict=True):
            row = {
                "state": block.state,
                "items": _counts(block),
                "metrics": block.metrics,
            }
            zeros = zero_only(row)
            if zeros and measured:
                block.warnings.append(
                    "Cero registrado: la fuente anota esta acción en este partido."
                )
            elif block.state in HIDDEN_STATES or zeros:
                reason = (
                    "Sólo contadores en cero y la fuente no tiene perfil medido; "
                    "no se acredita ausencia."
                    if zeros
                    else _reason(block)
                )
                discarded.append(
                    Discarded(
                        insight_id=block.insight_id,
                        team_id=spec["parameters"].get("team_id"),
                        reason=reason,
                    )
                )
                continue
            kept.append(spec)
            shown.append(
                ShownBlock(
                    id=block.id,
                    insight_id=block.insight_id,
                    title=block.title,
                    state=block.state,
                    warnings=block.warnings,
                    metrics=stable_metrics(
                        block.metrics,
                        [data.evidence[i] for i in spec["evidence_ids"]],
                    ),
                    evidence_ids=spec["evidence_ids"],
                )
            )
        candidates = kept

    html = manifest = None
    if candidates:
        html, manifest = await _render(plan, data, candidates, title)
    used = {i for b in candidates for i in b["evidence_ids"]}
    return Composition(
        plan=plan,
        title=title,
        html=html,
        manifest=manifest,
        blocks=shown,
        discarded=discarded,
        api_errors=api_errors,
        evidence_count=len(used),
    )


def _evidence(data, blocks):
    ids = dict.fromkeys(i for b in blocks for i in b["evidence_ids"])
    return [data.evidence[i] for i in ids]


async def _render(plan, data, blocks, title):
    """Valida y renderiza con el MCP de insights, como lo haría cualquier anfitrión."""
    teams = [
        {"team_id": team_id, "color": color}
        for team_id, color in zip(
            (plan.home_team_id, plan.away_team_id),
            TEAM_COLORS,
            strict=True,
        )
    ]
    report = {
        "title": title,
        "template_id": plan.intent.template_id,
        "blocks": blocks,
        "teams": teams,
    }
    # El contexto del partido (ya consultado por el resolvedor) da nombres y
    # dorsales a los gráficos; el MCP lo conserva aunque ningún bloque lo declare.
    context = [
        e
        for e in data.evidence.values()
        if e["operation"] == "get_match_context"
        and e["arguments"].get("match_id") == plan.intent.match_id
    ][:1]
    evidence = _evidence(data, blocks)
    known = {e["evidence_id"] for e in evidence}
    evidence += [e for e in context if e["evidence_id"] not in known]
    options = {
        "zero_only_insights": plan.zero_only_insights,
        "unannotated_metrics": plan.unannotated_metrics,
    }
    async with Client(create_server(evidence, render_options=options)) as client:
        checked = (await client.call_tool("validate_report", report)).structured_content
        if not checked or not checked.get("valid"):
            raise ValueError("INVALID_REPORT_PLAN")
        rendered = await client.call_tool("render_report", report)
        if rendered.is_error:
            raise ValueError("REPORT_RENDER_FAILED")
        uri = rendered.structured_content["resource_uri"]
        html = (await client.read_resource(uri)).contents[0].text
    # El manifiesto lleva las decisiones del anfitrión: quien lo vuelva a renderizar
    # (la web) debe aplicar el mismo perfil de fuente que el render del MCP.
    return html, {**report, **options, "evidence": evidence}
