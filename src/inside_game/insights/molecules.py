"""Moléculas: lecturas, leyendas, avisos y tablas que comparten los organismos."""

import json
import re

from .atoms import numeric, tag, text
from .labels import clean_key, column_label, metric_label


def legend(items):
    """Color + texto: la identidad no depende únicamente del color."""
    return (
        '<ul class="chart-legend" aria-label="Legend">'
        + "".join(
            f'<li><span class="legend-key" style="background:{color}"></span>{text(label)}</li>'
            for color, label in dict.fromkeys(items)
        )
        + "</ul>"
        if items
        else ""
    )


def metric_value(label, value):
    key = clean_key(label)
    if key.endswith(("_rate", "_fraction")) and type(value) in (int, float):
        return f"{value:.1%}"
    return numeric(value)


def metric_reading(label, value, teams=None):
    return f'<div class="reading"><dt>{text(metric_label(label, teams))}</dt><dd>{metric_value(label, value)}</dd></div>'


def team_breakdown(by_team, teams):
    """Una fila por equipo, una columna por cifra: quién es quién sin mirar colores."""
    if not by_team:
        return ""
    columns = list(dict.fromkeys(k for row in by_team.values() for k in row))
    head = "".join(
        f"<th>{text(metric_label(k, teams).removeprefix('Events · '))}</th>"
        for k in columns
    )
    rows = []
    for team_id, row in by_team.items():
        info = (teams or {}).get(team_id, {})
        name = info.get("name", f"Team {team_id}")
        color = info.get("color", "#52675f")
        cells = "".join(f"<td>{metric_value(k, row.get(k))}</td>" for k in columns)
        rows.append(
            f'<tr><td class="team-name"><span class="legend-key" style="background:{text(color)}"></span>{text(name)}</td>{cells}</tr>'
        )
    return (
        '<div class="table-scroll"><table class="team-breakdown"><caption>By team</caption>'
        f"<thead><tr><th>Team</th>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def metrics(values, teams=None):
    if not values:
        return ""
    diagnostic = {
        "heatmap_scale_max",
        "events_in_supplied_evidence",
        "sample_time_ms",
        "reconstruction_error",
        "orthogonality_error",
    }
    ordered = [
        (k, v)
        for k, v in values.items()
        if k not in diagnostic and not k.endswith("_id")
    ]
    selected = ordered[:4]
    remaining = [(k, v) for k, v in values.items() if (k, v) not in selected]
    note = (
        '<details class="metric-details"><summary>More metrics & diagnostics</summary><dl class="metrics">'
        + "".join(metric_reading(k, v, teams) for k, v in remaining)
        + "</dl></details>"
        if remaining
        else ""
    )
    return (
        '<dl class="metrics">'
        + "".join(metric_reading(k, v, teams) for k, v in selected)
        + "</dl>"
        + note
    )


def warnings(items):
    if not items:
        return ""
    return (
        '<details class="source-notes"><summary>Source notes & limitations (original language)</summary><ul>'
        + "".join(f"<li>{text(w)}</li>" for w in items)
        + "</ul></details>"
    )


def display_evidence_id(value):
    """ID visible sin los prefijos internos de transporte o verificación."""
    return re.sub(r"^(?:(?:r|a)\d+-)+", "", value)


def evidence_links(ids):
    return (
        '<p class="evidence-links">Evidence: '
        + ", ".join(
            f'<a href="#evidence-{text(e)}">{text(display_evidence_id(e))}</a>'
            for e in ids
        )
        + "</p>"
    )


def data_table(rows):
    if not rows:
        return ""
    rows = [r if isinstance(r, dict) else {"value": r} for r in rows]
    keys = list(dict.fromkeys(k for r in rows[:100] for k in r))[:8]

    def cell(v):
        if isinstance(v, (dict, list)):
            return text(json.dumps(v, ensure_ascii=False))
        return "—" if v is None else text(v)

    heading = "".join(f'<th scope="col">{text(column_label(k))}</th>' for k in keys)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell(row.get(k))}</td>" for k in keys) + "</tr>"
        for row in rows[:100]
    )
    count_label = "row" if len(rows) == 1 else "rows"
    return f'<details class="data-table"><summary>Data table · {len(rows)} {count_label}</summary><div class="table-scroll"><table><thead><tr>{heading}</tr></thead><tbody>{body}</tbody></table></div><p class="muted">Showing up to 100 rows and 8 columns. Full data is included in the JSON download.</p></details>'


# --- Espacio de trabajo: mensajes de la conversación ---


def chat_message(role, inner):
    """Entrada de la conversación; `inner` ya está compuesto por átomos."""
    return f'<li class="msg {text(role)}">{inner}</li>'


def source_tag(synthetic, provider=None):
    if synthetic:
        return tag("Synthetic data", "synthetic")
    return tag(f"Recorded data · {provider or 'recorded source'}", "real")


def answer_card(title, source, pieces, notes=(), missing=(), has_report=False):
    """Respuesta de un informe: qué se muestra, qué no y por qué."""
    count = len(pieces)
    shown = (
        f"<p>{'Se muestra 1 pieza' if count == 1 else f'Se muestran {count} piezas'}:</p>"
        + '<ul class="pieces">'
        + "".join(f"<li>{text(p)}</li>" for p in pieces)
        + "</ul>"
        if pieces
        else "<p>No hay piezas que mostrar con los datos de esta fuente.</p>"
    )
    absent = (
        '<details class="missing"><summary>'
        + (
            "1 pieza no disponible"
            if len(missing) == 1
            else f"{len(missing)} piezas no disponibles"
        )
        + "</summary><ul>"
        + "".join(
            f"<li><strong>{text(n)}</strong> — {text(r)}</li>" for n, r in missing
        )
        + "</ul></details>"
        if missing
        else ""
    )
    view = (
        '<button type="button" class="link view-report">Ver informe</button>'
        if has_report
        else ""
    )
    return chat_message(
        "answer",
        f'<p class="answer-title">{text(title)}</p>{source}{shown}'
        + "".join(f'<p class="note">{text(n)}</p>' for n in notes)
        + absent
        + view,
    )


def clarification_card(question, options=()):
    buttons = "".join(
        f'<button type="button" data-question="{text(o)}">{text(o)}</button>'
        for o in options
    )
    return chat_message(
        "clarification",
        f"<p>{text(question)}</p>"
        + (f'<div class="options">{buttons}</div>' if buttons else ""),
    )


def notice_card(kind, message, codes=()):
    """Rechazo, error o aviso; los códigos quedan plegados en «Detalles»."""
    details = (
        f'<details><summary>Detalles</summary><p class="codes">{text(" · ".join(codes))}</p></details>'
        if codes
        else ""
    )
    return chat_message(kind, f"<p>{text(message)}</p>{details}")
