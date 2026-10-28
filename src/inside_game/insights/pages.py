"""Página = template + organismos + datos originales. No hace I/O ni inferencia."""

import base64
import hashlib
import json
import time

from .adapters import prepare
from .analysis_note import analyst_copy
from .atoms import text
from .catalog import RECIPES
from .contracts import ReportSpec
from .identity import identities
from .molecules import evidence_links, legend
from .organisms import (
    about,
    ask_panel,
    conversation,
    evidence_footer,
    insight_section,
    masthead,
    report_canvas,
)
from .templates import CSS, JS


def compile_report(request):
    spec = ReportSpec.model_validate(request)
    zero_only = set(spec.zero_only_insights)
    unannotated = {k: set(v) for k, v in spec.unannotated_metrics.items()}
    blocks = [
        prepare(b, spec.evidence, zero_only, unannotated.get(b.insight_id, ()))
        for b in spec.blocks
    ]
    teams, players = identities(spec)
    for block in blocks:
        block.teams = teams
        block.players = players
    heat_scales = {}
    for block in blocks:
        cells = [p["value"] for p in block.polygons if p.get("cell")]
        if cells:
            heat_scales[block.unit] = max(heat_scales.get(block.unit, 0), *cells)
    for block in blocks:
        if any(p.get("cell") for p in block.polygons):
            block.metrics["heatmap_scale_max"] = heat_scales[block.unit]
    return spec, blocks


FOOTER = "Data and provenance are included. Geometric measures are not probabilities or calibrated tactical scores. Methods inspired by FIFA and research papers disclose their local adaptations."


def report_parts(request):
    """Página sin envoltorio: cabecera, cuerpo, pie y datos.

    `render_report` la envuelve en un documento autocontenido; una aplicación
    puede insertar las mismas piezas en su propia página (mismo HTML, mismos
    organismos) e inicializarlas con el JS de los templates.
    """
    spec, blocks = compile_report(request)
    teams, _ = identities(spec)
    payload = {
        "schema_version": "1",
        "title": spec.title,
        "template_id": spec.template_id,
        "teams": teams,
        "analyst": spec.analyst.model_dump(mode="json") if spec.analyst else None,
        "blocks": [b.model_dump(mode="json") for b in blocks],
        "evidence": [e.model_dump(mode="json") for e in spec.evidence],
    }
    # JSON dentro de script no debe permitir cerrar el elemento ni inyectar HTML.
    encoded = (
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    options = '<option value="all">Full report</option>' + "".join(
        f'<option value="{text(b.id)}">{text(b.title)}</option>' for b in blocks
    )
    body = "".join(
        insight_section(b, RECIPES[b.insight_id]["organism_family"]) for b in blocks
    )
    if spec.analyst:
        body = (
            '<section class="analyst-note"><h2>Analyst findings</h2>'
            + analyst_copy(spec.analyst.text)
            + (
                evidence_links(spec.analyst.evidence_ids)
                if spec.analyst.evidence_ids
                else ""
            )
            + "</section>"
            + body
        )
    kinds = sorted(
        {
            "Synthetic"
            if e.response.provenance.get("is_synthetic") is True
            else "Recorded · see provider"
            if e.response.provenance.get("is_synthetic") is False
            else "Provenance not specified"
            for e in spec.evidence
        }
    )
    match = next(
        (
            e.response.data.get("match", {})
            for e in spec.evidence
            if e.operation == "get_match_context"
        ),
        {},
    )
    scoreboard = ""
    if match:
        home = teams.get(str(match.get("home_team_id")), {})
        away = teams.get(str(match.get("away_team_id")), {})
        scoreboard = f'<div class="match-banner"><div><span class="eyebrow">Home</span><strong style="--team:{home.get("color", "#2463bc")}">{text(home.get("name", "Home"))}</strong></div><p class="score">{text(match.get("home_score", "—"))}<span>:</span>{text(match.get("away_score", "—"))}</p><div><span class="eyebrow">Away</span><strong style="--team:{away.get("color", "#bf402e")}">{text(away.get("name", "Away"))}</strong></div></div>'
    team_legend = legend([(v["color"], v["name"]) for v in teams.values()])
    header = (
        f'<p>Inside the game · Match analysis</p><h1>{text(spec.title)}</h1><p class="intro">Match evidence, charts and methods in a report you can explore offline.</p><p class="report-meta">{len(blocks)} blocks · {len(spec.evidence)} evidence sources · {text(" / ".join(kinds))}</p>'
        + scoreboard
        + team_legend
        + '<p class="palette-note">Report colours identify the teams; they are not official club colours.</p>'
        + f'<div class="toolbar"><label>Show <select id="block-filter">{options}</select></label><button id="download-data" type="button">Download data</button><button id="print-report" type="button">Print</button></div>'
    )
    return {
        "spec": spec,
        "blocks": blocks,
        "payload": payload,
        "payload_json": encoded,
        "header": header,
        "main": body + evidence_footer(spec.evidence),
        "footer": FOOTER,
        "template_id": spec.template_id,
    }


def render_report(request):
    started = time.perf_counter()
    parts = report_parts(request)
    spec, blocks = parts["spec"], parts["blocks"]
    script_hash = base64.b64encode(hashlib.sha256(JS.encode()).digest()).decode()
    csp = f"default-src 'none'; style-src 'unsafe-inline'; script-src 'sha256-{script_hash}'; connect-src 'none'; img-src data:; base-uri 'none'; form-action 'none'"
    document = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="{text(csp)}"><title>{text(spec.title)}</title><style>{CSS}</style></head><body><header>{parts["header"]}</header><main class="report {text(parts["template_id"])}">{parts["main"]}</main><footer>{parts["footer"]}</footer><script type="application/json" id="report-data">{parts["payload_json"]}</script><script>{JS}</script></body></html>'''
    size = len(document.encode())
    if size > 16 * 1024 * 1024:
        raise ValueError("REPORT_SIZE_EXCEEDED")
    return {
        "html": document,
        "bytes": size,
        "render_ms": round((time.perf_counter() - started) * 1000, 3),
        "blocks": [
            {
                "id": b.id,
                "insight_id": b.insight_id,
                "state": b.state,
                "warnings": b.warnings,
            }
            for b in blocks
        ],
    }


def render_workspace(groups, recipes, model_available, details, suggestions=()):
    """Página de la aplicación: template «espacio de trabajo» + sus organismos.

    CSS y JS se sirven como archivos (`/assets/insights.css` y `.js`, que incluyen
    los de los informes): la página no lleva scripts en línea.
    """
    intro = (
        "Pregunta por un partido, un equipo, un jugador o un momento concreto."
        if model_available
        else "Elige un partido y el tipo de informe que quieres ver."
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Inside the Game · Insights de partido</title>"
        '<link rel="stylesheet" href="/assets/insights.css">'
        '<script src="/assets/insights.js" defer></script></head>'
        f'<body class="workspace">{masthead()}<div class="desk">'
        '<section class="console" aria-label="Pedir un informe">'
        f"{conversation(intro, suggestions if model_available else ())}"
        f"{ask_panel(groups, recipes, model_available)}{about(details)}</section>"
        '<section class="canvas" id="canvas" aria-label="Informe">'
        '<div class="canvas-bar"><div class="canvas-title"><h2 id="report-title">Informe</h2>'
        '<span id="report-tag"></span></div>'
        '<a id="report-open" href="#" target="_blank" rel="noopener" hidden>Abrir en otra pestaña</a></div>'
        '<div class="canvas-wrap" id="canvas-wrap"><div class="canvas-loading" id="canvas-loading" hidden>'
        '<p class="spinner">Preparando el informe…</p></div>'
        f"{report_canvas()}</div></section></div></body></html>"
    )
