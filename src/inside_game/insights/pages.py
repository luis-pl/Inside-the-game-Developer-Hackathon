"""Página = template + organismos + datos originales. No hace I/O ni inferencia."""

import base64
import hashlib
import json
import time

from .adapters import prepare
from .atoms import text
from .catalog import RECIPES
from .contracts import ReportSpec
from .identity import identities
from .molecules import legend
from .organisms import evidence_footer, insight_section
from .templates import CSS, JS


def compile_report(request):
    spec = ReportSpec.model_validate(request)
    blocks = [prepare(b, spec.evidence) for b in spec.blocks]
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


def render_report(request):
    started = time.perf_counter()
    spec, blocks = compile_report(request)
    teams, _ = identities(spec)
    payload = {
        "schema_version": "1",
        "title": spec.title,
        "template_id": spec.template_id,
        "teams": teams,
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
    script_hash = base64.b64encode(hashlib.sha256(JS.encode()).digest()).decode()
    csp = f"default-src 'none'; style-src 'unsafe-inline'; script-src 'sha256-{script_hash}'; connect-src 'none'; img-src data:; base-uri 'none'; form-action 'none'"
    options = '<option value="all">Informe completo</option>' + "".join(
        f'<option value="{text(b.id)}">{text(b.title)}</option>' for b in blocks
    )
    body = "".join(
        insight_section(b, RECIPES[b.insight_id]["organism_family"]) for b in blocks
    )
    kinds = sorted(
        {
            "Sintético"
            if e.response.provenance.get("is_synthetic")
            else "Real · consultar proveedor"
            for e in spec.evidence
        }
    )
    document = f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="{text(csp)}"><title>{text(spec.title)}</title><style>{CSS}</style></head><body><header><p>Inside the game · Informe deportivo</p><h1>{text(spec.title)}</h1><p class="intro">Evidencia del partido, gráficos y métodos en un documento que puedes explorar sin conexión.</p><p class="report-meta">{len(blocks)} bloques · {len(spec.evidence)} evidencias · {text(" / ".join(kinds))}</p><div class="toolbar"><label>Mostrar <select id="block-filter">{options}</select></label><button id="download-data" type="button">Descargar datos</button><button id="print-report" type="button">Imprimir</button></div></header><main class="report {text(spec.template_id)}">{body}{evidence_footer(spec.evidence)}</main><footer>Datos y procedencia incluidos. Los cálculos geométricos no son probabilidades ni puntuaciones tácticas calibradas. Las familias inspiradas en FIFA y papers declaran su adaptación local.</footer><script type="application/json" id="report-data">{encoded}</script><script>{JS}</script></body></html>'''
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
        scoreboard = f'<div class="match-banner"><div><span class="eyebrow">Local</span><strong style="--team:{home.get("color", "#2463bc")}">{text(home.get("name", "Local"))}</strong></div><p class="score">{text(match.get("home_score", "—"))}<span>:</span>{text(match.get("away_score", "—"))}</p><div><span class="eyebrow">Visitante</span><strong style="--team:{away.get("color", "#bf402e")}">{text(away.get("name", "Visitante"))}</strong></div></div>'
    team_legend = legend([(v["color"], v["name"]) for v in teams.values()])
    document = document.replace(
        '<div class="toolbar">',
        scoreboard
        + team_legend
        + '<p class="palette-note">Paleta configurada para este informe; no representa colores oficiales.</p><div class="toolbar">',
        1,
    )
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
