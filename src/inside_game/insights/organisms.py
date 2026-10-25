"""Organismos SVG, redes, series, replay y evidencia; sin dependencias remotas."""

import json

from .atoms import MARKINGS, numeric, status, text
from .catalog import RECIPES
from .charts import energy_composition, pitch, possession_timeline, series
from .identity import team
from .molecules import data_table, evidence_links, legend, metrics, warnings


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
            f'<line x1="{20 + float(b["birth_m"]) * 14}" y1="{15 + i * 12}" x2="{20 + (float(death) if death is not None else 40) * 14}" y2="{15 + i * 12}" stroke="{["#2463bc", "#bf402e"][min(1, int(b["dimension"]))]}" stroke-width="3"><title>H{text(b["dimension"])}: {text(b["birth_m"])}–{text(death) if death is not None else "censurado a 40 m"}</title></line>'
        )
    return f'<figure><svg viewBox="0 0 600 {height}" role="img" aria-label="Intervalos de persistencia">{"".join(marks)}</svg>{legend([("#2463bc", "H0 · componentes"), ("#bf402e", "H1 · ciclos")])}<figcaption>Escala de distancia en metros; intervalos sin muerte observada están censurados a 40 m.</figcaption></figure>'


def replay(block):
    if not block.frames:
        return ""
    return f'<div class="replay" data-block="{text(block.id)}"><svg class="pitch replay-field" viewBox="-4 -4 113 76" role="img" aria-label="Posiciones observadas"><g class="field-lines">{MARKINGS}</g><g class="replay-points"></g></svg><div class="replay-controls"><button type="button" class="play">Reproducir</button><label>Observación <input class="seek" type="range" min="0" max="{len(block.frames) - 1}" value="0"/></label><output aria-live="off"></output></div><p class="muted">1× = tiempo real. Sin interpolar; las ausencias permanecen vacías.</p></div>'


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
    if block.insight_id == "hodge_flow":
        visual += energy_composition(block)
    if family == "comparison" or block.insight_id == "node_robustness":
        visual += comparison_bars(block)
    if family == "sequence":
        visual += sequence_strip(block)
    empty = (
        '<p class="empty-note">No hay un gráfico compatible con la evidencia suministrada. Consulta los límites y el estado del bloque.</p>'
        if not visual and block.state != "ready"
        else ""
    )
    return f'<section class="insight" id="{text(block.id)}" data-insight="{text(block.insight_id)}" data-span="{block.visual.span}"><div class="section-heading"><h2>{text(block.title)}</h2>{status(block.state)}</div><p class="block-question">{text(RECIPES[block.insight_id].get("question", "Lectura calculada sobre la evidencia y el alcance seleccionados."))}</p>{metrics(block.metrics, block.teams)}{visual}{empty}{data_table(block.rows)}{warnings(block.warnings)}<p class="method">Método: {text(block.method_id)}</p>{evidence_links(block.evidence_ids)}</section>'


def comparison_bars(block):
    from .adapters import flatten_metrics, number

    rows = []
    for row in block.rows:
        if not isinstance(row, dict):
            continue
        values = flatten_metrics(row.get("metrics", row))
        values = {
            k: v for k, v in values.items() if number(v) and not k.endswith("_id")
        }
        label = row.get(
            "entity_id", row.get("player_id", row.get("removed_player_id", "Entidad"))
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
            f'<figure><svg class="series" viewBox="0 0 690 {40 + len(selected) * 30}" role="img" aria-label="{text(field)}">{"".join(marks)}</svg><figcaption>{text(field)} · escala compartida, origen cero; sólo valores disponibles.</figcaption></figure>'
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
                    f'<article class="possession-card" style="--team:{identity["color"]}"><span class="eyebrow">P{text(row.get("period"))} · {start / 60000:.1f}′–{end / 60000:.1f}′</span><strong>{text(identity["name"])}</strong><p>{text(row.get("passes", "—"))} pases · {text(row.get("shots", "—"))} tiros · {(end - start) / 1000:g} s de tramo registrado</p></article>'
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


def evidence_footer(evidence):
    return (
        '<section class="evidence-footer"><h2>Fuentes y alcance</h2>'
        + "".join(
            f'<details id="evidence-{text(e.evidence_id)}"><summary>{text(e.evidence_id)} · {text(e.operation)} · {"sintético" if e.response.provenance.get("is_synthetic") else "real"}</summary><pre>{text(json.dumps({"arguments": e.arguments, "scope": e.response.scope, "provenance": e.response.provenance, "coverage": e.response.coverage, "coordinates": e.response.coordinates, "warnings": e.response.warnings}, ensure_ascii=False, indent=2))}</pre></details>'
            for e in evidence
        )
        + "</section>"
    )
