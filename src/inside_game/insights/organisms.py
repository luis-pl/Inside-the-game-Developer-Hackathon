"""Organismos SVG, redes, series, replay y evidencia; sin dependencias remotas."""

import json
import re

from .atoms import MARKINGS, numeric, status, text
from .catalog import RECIPES
from .charts import energy_composition, pitch, possession_timeline, series
from .headlines import headline
from .identity import team
from .labels import metric_label
from .molecules import (
    data_table,
    display_evidence_id,
    evidence_links,
    legend,
    metrics,
    team_breakdown,
    warnings,
)


def barcode(block):
    bars = [r for r in block.rows if "birth_m" in r]
    if not bars:
        return ""
    height = max(60, min(60, len(bars)) * 12 + 45)
    marks = [
        f'<text x="{20 + v * 14}" y="{height - 5}" font-size="10" fill="#51645e">{v} m</text><path d="M{20 + v * 14} 5V{height - 22}" stroke="#dce3dc" stroke-width=".5"/>'
        for v in (0, 10, 20, 30, 40)
    ]
    for i, b in enumerate(bars[:60]):
        death = b.get("death_m")
        marks.append(
            f'<line x1="{20 + float(b["birth_m"]) * 14}" y1="{15 + i * 12}" x2="{20 + (float(death) if death is not None else 40) * 14}" y2="{15 + i * 12}" stroke="{["#2463bc", "#bf402e"][min(1, int(b["dimension"]))]}" stroke-width="3"><title>H{text(b["dimension"])}: {text(b["birth_m"])}–{text(death) if death is not None else "censored at 40 m"}</title></line>'
        )
    return f'<figure><svg viewBox="0 0 600 {height}" role="img" aria-label="Persistence intervals">{"".join(marks)}</svg>{legend([("#2463bc", "H0 · components"), ("#bf402e", "H1 · cycles")])}<figcaption>Distance scale in metres; intervals with no observed death are censored at 40 m.</figcaption></figure>'


def replay(block):
    if not block.frames:
        return ""
    return f'<div class="replay" data-block="{text(block.id)}"><svg class="pitch replay-field" viewBox="-4 -4 113 76" role="img" aria-label="Observed positions"><g class="field-lines">{MARKINGS}</g><g class="replay-points"></g></svg><div class="replay-controls"><button type="button" class="play">Play</button><label>Sample <input class="seek" type="range" min="0" max="{len(block.frames) - 1}" value="0"/></label><output aria-live="off"></output></div><p class="muted">1× = real time. No interpolation; missing observations stay empty.</p></div>'


def insight_section(block, family):
    visual = (
        replay(block)
        if block.frames
        else pitch(
            block, network=family == "network" or block.insight_id == "passing_network"
        )
    )
    visual += series(block) + barcode(block)
    if block.insight_id in {"match_timeline", "sequence_explorer"}:
        visual += possession_timeline(block)
    if block.markers:
        visual += key_moments(block)
    if block.insight_id == "hodge_flow":
        visual += energy_composition(block)
    if family == "comparison" or block.insight_id == "node_robustness":
        visual += comparison_bars(block)
    if family == "sequence":
        visual += sequence_strip(block)
    empty = (
        '<p class="empty-note">No compatible chart is available for this evidence. Check the block status and limitations.</p>'
        if not visual and block.state != "ready"
        else ""
    )
    return f'<section class="insight" id="{text(block.id)}" data-insight="{text(block.insight_id)}" data-span="{block.visual.span}"><div class="section-heading"><h2>{text(block.title)}</h2>{status(block.state)}</div><p class="block-question">{text(RECIPES[block.insight_id].get("question", "Calculated from the selected evidence and scope."))}</p>{answer_line(block)}{metrics(block.metrics, block.teams)}{team_breakdown(block.by_team, block.teams)}{visual}{empty}{data_table(block.rows)}{warnings(block.warnings)}<p class="method">Method: {text(block.method_id)}</p>{evidence_links(block.evidence_ids)}</section>'


MOMENT_LABELS = {"goal": "Goal", "substitution": "Substitution", "card": "Card"}


def answer_line(block):
    """La cifra que responde la pregunta de la pieza, justo debajo de ella."""
    line = headline(block)
    return f'<p class="block-answer">{text(line)}</p>' if line else ""


def key_moments(block):
    items = []
    for m in block.markers[:40]:
        who = block.players.get(str(m.get("player_id")), {}).get("name")
        parts = [
            f"P{m['period']} {m['time_ms'] // 60000}′",
            m.get("label") or MOMENT_LABELS[m["kind"]],
            team(block, m.get("team_id"))["name"],
        ] + ([who] if who else [])
        items.append(f"<li>{text(' · '.join(parts))}</li>")
    more = len(block.markers) - 40
    note = f" Showing the first 40 of {len(block.markers)}." if more > 0 else ""
    return (
        f'<details class="moments"><summary>Goals, substitutions & cards ({len(block.markers)})</summary>'
        f'<figure><ol class="event-chain">{"".join(items)}</ol>'
        f"<figcaption>As recorded by the source.{note}</figcaption></figure></details>"
    )


def entity_name(block, key):
    """Nombre de un team o jugador comparado, no su identificador."""
    if str(key) in block.teams:
        return block.teams[str(key)]["name"]
    player = block.players.get(str(key), {})
    return player.get("name") or str(key)


def comparison_bars(block):
    from .adapters import flatten_metrics, is_unknown_metric, number

    rows = []
    for row in block.rows:
        if not isinstance(row, dict):
            continue
        values = flatten_metrics(row.get("metrics", row))
        values = {
            k: v
            for k, v in values.items()
            if number(v) and not k.endswith("_id") and not is_unknown_metric(k)
        }
        label = entity_name(
            block,
            row.get(
                "entity_id",
                row.get("player_id", row.get("removed_player_id", "Entity")),
            ),
        )
        rows.append((label, values))
    fields = list(dict.fromkeys(k for _, values in rows for k in values))[:4]
    figures = []
    for field in fields:
        selected = [
            (label, values[field]) for label, values in rows if field in values
        ][:20]
        if len(selected) < 2:
            continue
        low = min(0, min(v for _, v in selected))
        high = max(0, max(v for _, v in selected))
        span = high - low or 1
        origin = 160 + 420 * (0 - low) / span
        marks = []
        for i, (label, value) in enumerate(selected):
            x = 160 + 420 * (value - low) / span
            y = 20 + i * 30
            marks.append(
                f'<text x="5" y="{y + 14}">{text(label)}</text><rect x="{min(origin, x):.3f}" y="{y}" width="{abs(x - origin):.3f}" height="18" fill="#185540"/><text x="600" y="{y + 14}">{numeric(value)}</text>'
            )
        figures.append(
            f'<figure><svg class="series" viewBox="0 0 690 {40 + len(selected) * 30}" role="img" aria-label="{text(metric_label(field, block.teams))}">{"".join(marks)}</svg><figcaption>{text(metric_label(field, block.teams))} · shared scale, zero baseline; available values only.</figcaption></figure>'
        )
    return "".join(figures)


def sequence_strip(block):
    chains = []
    for row in block.rows[:8]:
        if not isinstance(row, dict):
            continue
        ids = row.get("event_ids", [])
        if ids:
            start, end = row.get("start_ms"), row.get("end_ms")
            if start is not None and end is not None:
                identity = team(block, row.get("team_id"))
                chains.append(
                    f'<article class="possession-card" style="--team:{identity["color"]}"><span class="eyebrow">P{text(row.get("period"))} · {start / 60000:.1f}′–{end / 60000:.1f}′</span><strong>{text(identity["name"])}</strong><p>{text(row.get("passes", "—"))} passes · {text(row.get("shots", "—"))} shots · {(end - start) / 1000:g} s of recorded sequence</p></article>'
                )
                continue
            chains.append(
                '<ol class="event-chain">'
                + "".join(f"<li>{text(i)}</li>" for i in ids)
                + "</ol>"
            )
    return (
        '<div class="possession-cards">' + "".join(chains) + "</div>" if chains else ""
    )


def evidence_item(e, label):
    detail = json.dumps(
        {
            "arguments": e.arguments,
            "scope": e.response.scope,
            "provenance": e.response.provenance,
            "coverage": e.response.coverage,
            "coordinates": e.response.coordinates,
            "warnings": e.response.warnings,
        },
        ensure_ascii=False,
        indent=2,
    )
    return f'<details id="evidence-{text(e.evidence_id)}"><summary>{text(label)}</summary><pre>{text(detail)}</pre></details>'


def evidence_summary(evidence, queries):
    synthetic = {e.response.provenance.get("is_synthetic") for e in evidence}
    providers = sorted(
        {
            d.get("provider")
            for e in evidence
            for d in e.response.provenance.get("datasets", [])
            if isinstance(d, dict) and d.get("provider")
        }
    )
    if synthetic == {True}:
        source = "SYNTHETIC demonstration data"
    elif synthetic == {False}:
        source = "Recorded data" + (
            f" from {', '.join(providers)}" if providers else ""
        )
    elif synthetic == {True, False}:
        source = "Recorded and synthetic data"
    else:
        source = "Mixed or unspecified provenance"
    pages = f" ({len(evidence)} pages)" if len(evidence) != queries else ""
    return f"{source} · {queries} queries{pages}. Each retains its original arguments, scope, coverage and warnings."


def evidence_footer(evidence):
    """Trazabilidad: una consulta por fila (sus pages dentro), todo plegado."""
    groups = {}
    for e in evidence:
        match = re.match(r"^(.+)-p(\d+)$", e.evidence_id)
        key = match.group(1) if match else e.evidence_id
        groups.setdefault(key, []).append((e, match.group(2) if match else None))
    rows = []
    for key, pages in groups.items():
        first = pages[0][0]
        flag = first.response.provenance.get("is_synthetic")
        kind = (
            "synthetic"
            if flag is True
            else "recorded"
            if flag is False
            else "unspecified"
        )
        head = f"{display_evidence_id(key)} · {first.operation} · {kind}"
        if len(pages) == 1:
            rows.append(evidence_item(first, head))
        else:
            rows.append(
                f'<details class="evidence-query"><summary>{text(head)} · {len(pages)} pages</summary>'
                + "".join(evidence_item(e, f"Page {n}") for e, n in pages)
                + "</details>"
            )
    return (
        '<section class="evidence-footer"><h2>Sources & scope</h2>'
        f'<p class="muted">{text(evidence_summary(evidence, len(groups)))}</p>'
        f'<details class="evidence-all"><summary>Inspect {len(groups)} data queries (audit)</summary>'
        + "".join(rows)
        + "</details></section>"
    )


# --- Espacio de trabajo: organismos de la aplicación web ---

REPORT_KINDS = (
    (
        "match_overview",
        "Resumen del partido",
        "Tiros, cronología, redes de pases y estructura.",
    ),
    ("entity_comparison", "Comparación de equipos", "Los dos equipos lado a lado."),
    (
        "tactical_episode",
        "Un momento del partido",
        "Posiciones, espacios y líneas en un instante.",
    ),
    ("custom_report", "Piezas a elegir", "Hasta seis visualizaciones concretas."),
)


def masthead():
    return (
        '<div class="masthead"><div class="brand"><h1>Inside the Game</h1>'
        "<p>Pide el análisis de un partido y recibe un informe visual con los datos que lo respaldan.</p></div>"
        '<button type="button" class="quiet" id="reset">Nueva conversación</button></div>'
    )


def conversation(intro, suggestions=()):
    buttons = "".join(
        f'<button type="button" data-question="{text(s)}">{text(s)}</button>'
        for s in suggestions
    )
    return (
        '<div class="thread-wrap"><ol class="thread" id="thread" aria-live="polite">'
        f'<li class="welcome" id="welcome"><h2>¿Qué quieres ver?</h2><p>{text(intro)}</p>'
        + (f'<div class="suggestions">{buttons}</div>' if buttons else "")
        + "</li></ol></div>"
    )


def match_select(groups):
    """`groups`: [(etiqueta, [(match_id, nombre, equipos)])]; sin IDs a la vista."""
    if not groups:
        return (
            '<p class="inline-error">No se pudo cargar la lista de partidos. '
            '<a href="/">Reintentar</a></p>'
        )
    options = "".join(
        f'<optgroup label="{text(label)}">'
        + "".join(
            f'<option value="{text(match_id)}" data-teams="{text(json.dumps(teams, ensure_ascii=False))}">{text(name)}</option>'
            for match_id, name, teams in matches
        )
        + "</optgroup>"
        for label, matches in groups
    )
    return f'<label class="field">Partido<select id="match" required>{options}</select></label>'


def ask_panel(groups, recipes, model_available):
    """Dos formas de pedir: texto (modelo) o formulario (sin modelo)."""
    ask_selected, pick_selected = (
        ("true", "false") if model_available else ("false", "true")
    )
    question = (
        '<textarea id="question" rows="2" maxlength="2000" placeholder="Por ejemplo: ¿quién creó más peligro, Frontend FC o Backend Rovers?"></textarea>'
        '<div class="compose-row"><p class="hint">Intro envía · Mayús+Intro, nueva línea</p>'
        '<button type="submit" class="primary" id="ask-button">Pedir informe</button></div>'
        if model_available
        else '<textarea id="question" rows="2" disabled placeholder="Las preguntas escritas no están disponibles ahora mismo."></textarea>'
        '<div class="compose-row"><p class="hint">Usa «Elegir informe».</p>'
        '<button type="submit" class="primary" id="ask-button" disabled>Pedir informe</button></div>'
    )
    kinds = "".join(
        f'<label class="kind"><input type="radio" name="template" value="{key}"'
        + (" checked" if n == 0 else "")
        + f"><span><strong>{text(title)}</strong><small>{text(hint)}</small></span></label>"
        for n, (key, title, hint) in enumerate(REPORT_KINDS)
    )
    pieces = "".join(
        f'<label><input type="checkbox" value="{text(key)}">{text(title)}</label>'
        for key, title in recipes
    )
    return (
        '<div class="compose"><div class="modes" role="tablist" aria-label="Forma de pedir">'
        f'<button type="button" role="tab" id="tab-ask" aria-controls="panel-ask" aria-selected="{ask_selected}">Preguntar</button>'
        f'<button type="button" role="tab" id="tab-pick" aria-controls="panel-pick" aria-selected="{pick_selected}">Elegir informe</button></div>'
        f'<div role="tabpanel" id="panel-ask" aria-labelledby="tab-ask"{"" if model_available else " hidden"}>'
        f'<form id="ask-form"><label for="question" class="visually-hidden">Tu pregunta</label>{question}</form></div>'
        f'<div role="tabpanel" id="panel-pick" aria-labelledby="tab-pick"{" hidden" if model_available else ""}>'
        f'<form id="intent-form" class="pick">{match_select(groups)}'
        f'<fieldset class="kinds"><legend>Tipo de informe</legend>{kinds}</fieldset>'
        '<div class="pair"><label class="field">Team<select id="team"><option value="">El local</option></select></label>'
        '<label class="field">Parte<select id="period"><option value="">Todo el partido</option>'
        '<option value="1">Primera parte</option><option value="2">Segunda parte</option></select></label></div>'
        '<label class="field" id="minute-field" hidden>Minuto dentro de esa parte'
        '<input type="number" id="minute" min="0" max="60" inputmode="numeric" placeholder="Por ejemplo, 20">'
        "<small>Si no indicas el minuto, se elige un instante con todos los jugadores visibles.</small></label>"
        '<fieldset class="recipes-box" id="recipes-field" hidden><legend>Piezas <span id="recipe-count">0 de 6</span></legend>'
        f'<div class="recipes" id="recipes">{pieces}</div></fieldset>'
        f'<button type="submit" class="primary" id="intent-button"{"" if groups else " disabled"}>Generar informe</button>'
        "</form></div></div>"
    )


def about(details):
    return (
        '<details class="about"><summary>Cómo funciona</summary><p>Cada informe se construye con datos '
        "consultados en el momento y muestra su fuente. Lo que una fuente no registra no se muestra, y el "
        "informe lo dice. Los partidos de demostración usan datos <strong>sintéticos</strong>.</p>"
        f"<p>{text(details)}</p></details>"
    )


def report_canvas(parts=None):
    """Lienzo: las mismas piezas que el informe exportado, o el estado vacío."""
    if parts is None:
        body = (
            '<div class="canvas-empty"><h3>El informe aparecerá aquí</h3><ul>'
            "<li><strong>Un partido:</strong> tiros, redes de pases, cronología y estructura.</li>"
            "<li><strong>Un jugador:</strong> movimiento, ocupación, pases y tiros.</li>"
            "<li><strong>Dos equipos:</strong> métricas y redes comparadas.</li>"
            "<li><strong>Un momento:</strong> posiciones, espacios y líneas en un instante.</li></ul></div>"
        )
    else:
        body = (
            f'<header>{parts["header"]}</header><main class="report {text(parts["template_id"])}">{parts["main"]}</main>'
            f'<footer>{parts["footer"]}</footer><script type="application/json" class="report-payload">{parts["payload_json"]}</script>'
        )
    return f'<div class="canvas-body" id="canvas-body">{body}</div>'
