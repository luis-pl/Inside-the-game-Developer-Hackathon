"""Organismos gráficos: SVG determinista sobre datos normalizados.

Las leyendas y etiquetas se componen con moléculas; no hay código generado,
descargas externas, inferencia de xG ni posiciones inventadas.
"""

from collections import defaultdict
from math import sqrt

from .atoms import MARKINGS, numeric, text
from .identity import player_label, team
from .molecules import legend


def pitch(block, network=False):
    if not any((block.points, block.vectors, block.polygons)):
        return ""
    schematic = block.layout == "schematic" or (
        network and block.insight_id != "passing_network"
    )
    shapes, team_ids = [], set()
    cells = [p for p in block.polygons if p.get("cell")]
    maximum = (
        block.metrics.get("heatmap_scale_max")
        or max((p.get("value", 0) for p in cells), default=1)
        or 1
    )
    for polygon in block.polygons:
        identity = team(block, polygon.get("team_id"))
        if polygon.get("team_id") is not None:
            team_ids.add(polygon["team_id"])
        color = identity["color"]
        if polygon.get("cell"):
            x, y, size = (
                float(polygon["x"]),
                float(polygon["y"]),
                float(polygon["size"]),
            )
            opacity = 0.08 + 0.85 * float(polygon["value"]) / maximum
            shapes.append(
                f'<rect x="{x}" y="{y}" width="{min(size, 105 - x)}" height="{min(size, 68 - y)}" fill="{color}" opacity="{opacity:.3f}"><title>{numeric(polygon["value"])} {text(block.unit)} · ({x:g}, {y:g}) m</title></rect>'
            )
        elif polygon.get("vertices"):
            pts = " ".join(
                f"{float(x):.4f},{float(y):.4f}" for x, y in polygon["vertices"]
            )
            shapes.append(
                f'<polygon points="{pts}" fill="{color}" fill-opacity=".19" stroke="{color}" stroke-opacity=".55" stroke-width=".22"><title>{text(identity["name"])} · jugador {text(polygon.get("player_id", "—"))} · {numeric(polygon.get("value"))} m²</title></polygon>'
            )
    weights = max((abs(v.get("weight", 1)) for v in block.vectors), default=1) or 1
    markers = set()
    for v in block.vectors[:1000]:
        if network and abs(v.get("weight", 1)) < block.visual.min_edge_weight:
            continue
        color = team(block, v.get("team_id"))["color"]
        team_ids.add(v.get("team_id"))
        x, y, ex, ey = (float(v[k]) for k in ("x", "y", "end_x", "end_y"))
        width = (
            0.12 + 0.7 * sqrt(abs(v.get("weight", 1)) / weights) if network else 0.27
        )
        # Curved directed network links expose reciprocal edges. Non-network
        # trajectories stay straight; only annotated failures get dashed lines.
        path = (
            f"M{x:.3f} {y:.3f} Q{(x + ex) / 2 - (ey - y) * 0.07:.3f} {(y + ey) / 2 + (ex - x) * 0.07:.3f} {ex:.3f} {ey:.3f}"
            if network
            else f"M{x:.3f} {y:.3f} L{ex:.3f} {ey:.3f}"
        )
        dash = 'stroke-dasharray="1.2 .9"' if v.get("failed") else ""
        marker = f"arrow-{block.id}-{color[1:]}"
        if marker not in markers:
            shapes.append(
                f'<defs><marker id="{marker}" viewBox="0 0 6 6" refX="8" refY="3" markerUnits="userSpaceOnUse" markerWidth="1.8" markerHeight="1.8" orient="auto-start-reverse"><path d="M0 0L6 3L0 6Z" fill="{color}"/></marker></defs>'
            )
            markers.add(marker)
        shapes.append(
            f'<path d="{path}" fill="none" stroke="{color}" stroke-width="{width:.3f}" stroke-opacity="{0.65 if network else 0.45}" {dash} marker-end="url(#{marker})"><title>{text(v.get("event_id", "Conexión"))} · {numeric(v.get("weight", 1))}</title></path>'
        )
    involvement = max((p.get("involvement", 1) for p in block.points), default=1) or 1
    for p in block.points[:1000]:
        key = p.get("player_id", p.get("id"))
        identity = team(block, p.get("team_id"))
        if p.get("team_id") is not None:
            team_ids.add(p["team_id"])
        color = identity["color"]
        x, y = float(p["x"]), float(p["y"])
        shot = block.insight_id == "shot_map"
        xg = p.get("xg")
        radius = (
            (sqrt(1 + 9 * max(0, xg))) if shot and isinstance(xg, (int, float)) else 1.2
        )
        if network:
            radius = 1.3 + 1.8 * sqrt(p.get("involvement", 1) / involvement)
        elif block.insight_id in {
            "space_partition",
            "team_shape",
            "proximity_network",
            "defensive_geometry",
        }:
            radius = 1.45
        outcome = p.get("outcome")
        hollow = shot and outcome not in {"Goal", "Saved", "Saved to Post"}
        tooltip = f"{identity['name']} · {block.players.get(str(key), {}).get('name', p.get('label', key or 'Acción'))}"
        if shot:
            if outcome and not str(outcome).lower().startswith("unknown"):
                tooltip += f" · {outcome}"
            if isinstance(xg, (int, float)):
                tooltip += f" · xG {numeric(xg)}"
        shapes.append(
            f'<circle cx="{x:.3f}" cy="{y:.3f}" r="{radius:.3f}" fill="{"#f4f6f2" if hollow else color}" stroke="{color if hollow else "#ffffff"}" stroke-width=".35"><title>{text(tooltip)}</title></circle>'
        )
        if outcome == "Goal":
            shapes.append(
                f'<circle cx="{x:.3f}" cy="{y:.3f}" r="{radius + 0.65:.3f}" fill="none" stroke="{color}" stroke-width=".28"/>'
            )
        labels = (
            block.visual.show_labels
            and key is not None
            and (
                network
                or block.insight_id
                in {
                    "space_partition",
                    "team_shape",
                    "proximity_network",
                    "defensive_geometry",
                }
            )
        )
        if labels:
            shapes.append(
                f'<text class="jersey" x="{x:.3f}" y="{y + 0.55:.3f}" text-anchor="middle">{text(player_label(block, key))}</text>'
            )
    caption = (
        "Red esquemática: las posiciones de nodos no representan ubicación en cancha."
        if schematic
        else "105 × 68 m"
    )
    if block.insight_id == "passing_network" and not schematic:
        caption += " · Nodos: media de acciones de pase y recepción; tamaño: participación; grosor: pases."
    elif block.insight_id == "space_partition":
        caption += " · Cercanía geométrica (Voronoi); no probabilidad de control. Puntos: tracking observado."
    elif block.coordinate_reference == "acting_team_attack":
        caption += " · Referencia de ataque de cada equipo →. No es la referencia fija del tracking."
    elif not schematic:
        caption += " · Posiciones observadas; consultar instante y alcance."
    if network:
        caption += f" Enlaces visibles con peso ≥ {block.visual.min_edge_weight}; las métricas conservan la red completa."
    if len(block.vectors) > 1000 or len(block.points) > 1000:
        caption += " Vista limitada a las primeras 1000 acciones; la evidencia completa está en el JSON."
    legends = [
        (team(block, key)["color"], team(block, key)["name"])
        for key in sorted(team_ids - {None}, key=str)
    ]
    if block.insight_id == "shot_map":
        caption += " Doble anillo: gol; relleno: parado; hueco: otro resultado o sin clasificar."
        caption += (
            " Área proporcional a xG con tamaño mínimo de lectura."
            if any(p.get("xg") is not None for p in block.points)
            else " Tamaño fijo: xG ausente."
        )
    scale = (
        f'<div class="heat-scale"><span>0</span><span class="heat-ramp" style="--team:{team(block, next(iter(team_ids - {None}), None))["color"]}"></span><span>{numeric(maximum)} {text(block.unit)}</span></div>'
        if cells
        else ""
    )
    field = "" if schematic else f'<g class="field-lines">{MARKINGS}</g>'
    return f'<figure class="pitch-figure"><svg class="pitch" viewBox="-4 -5 113 78" role="img" aria-label="{text(block.title)}">{field}<g class="layers">{"".join(shapes)}</g></svg>{scale}{legend(legends) if block.visual.show_legend else ""}<figcaption>{caption}</figcaption></figure>'


def possession_timeline(block):
    rows = [
        r for r in block.rows if "start_ms" in r and "end_ms" in r and "team_id" in r
    ]
    if not rows:
        return ""
    periods = sorted({r["period"] for r in rows})
    shapes, labels = [], []
    for pi, period in enumerate(periods):
        items = [r for r in rows if r["period"] == period]
        teams = sorted({r["team_id"] for r in items})
        end = max(r["end_ms"] for r in items) or 1
        top = 35 + pi * 125
        shapes.append(
            f'<text x="12" y="{top - 12}">P{period} · tiempo del período</text>'
        )
        for i, key in enumerate(teams):
            identity = team(block, key)
            y = top + i * 28
            shapes.append(
                f'<text x="12" y="{y + 14}">{text(identity["name"][:22])}</text><path d="M175 {y + 9}H660" stroke="#dde4e0"/>'
            )
            for row in items:
                if row["team_id"] != key:
                    continue
                x = 175 + 480 * row["start_ms"] / end
                width = max(0.8, 480 * (row["end_ms"] - row["start_ms"]) / end)
                shapes.append(
                    f'<rect x="{x:.2f}" y="{y}" width="{width:.2f}" height="18" rx="2" fill="{identity["color"]}"><title>{text(identity["name"])} · P{period} · {row["start_ms"] / 1000:g}–{row["end_ms"] / 1000:g} s · {row.get("passes", 0)} pases · {row.get("shots", 0)} tiros</title></rect>'
                )
            labels.append(
                (
                    identity["color"],
                    f"{identity['name']}: {sum(r['team_id'] == key for r in items)} secuencias en P{period}",
                )
            )
        shapes.append(
            f'<text x="175" y="{top + 80}">0′</text><text x="620" y="{top + 80}">{end / 60000:.1f}′</text>'
        )
    return f'<figure><svg class="series" viewBox="0 0 690 {30 + 125 * len(periods)}" role="img" aria-label="Secuencias de posesión registradas">{"".join(shapes)}</svg>{legend(labels)}<figcaption>Cada tramo une el primer y último evento de una posesión registrada. Los huecos se conservan. No equivale a porcentaje oficial de tiempo de posesión.</figcaption></figure>'


MARKER_NAMES = {"goal": "Gol", "substitution": "Cambio", "card": "Tarjeta"}
MARKER_LANE_Y = (226, 242)


def marker_marks(block, period, end):
    """Goles, cambios y tarjetas bajo el eje del tiempo, una franja por equipo."""
    marks = []
    teams = sorted({m.get("team_id") for m in block.markers}, key=str)
    for m in block.markers:
        if m["period"] != period:
            continue
        lane = MARKER_LANE_Y[min(teams.index(m.get("team_id")), 1)]
        x = 48 + 600 * m["time_ms"] / end
        identity = team(block, m.get("team_id"))
        color = identity["color"]
        label = m.get("label") or MARKER_NAMES.get(m["kind"], "Evento")
        who = block.players.get(str(m.get("player_id")), {}).get("name")
        tip = " · ".join(
            [f"P{period} {m['time_ms'] // 60000}′", label, identity["name"]]
            + ([who] if who else [])
        )
        if m["kind"] == "goal":
            shape = f'<circle cx="{x:.2f}" cy="{lane}" r="4.5" fill="{color}"/><circle cx="{x:.2f}" cy="{lane}" r="7.5" fill="none" stroke="{color}" stroke-width="1.5"/>'
        elif m["kind"] == "substitution":
            shape = f'<path d="M{x:.2f} {lane - 6}L{x + 6:.2f} {lane}L{x:.2f} {lane + 6}L{x - 6:.2f} {lane}Z" fill="{color}"/>'
        else:
            fill = "#c0392b" if "roja" in label.lower() else "#e0b000"
            shape = f'<rect x="{x - 3.5:.2f}" y="{lane - 6}" width="7" height="12" rx="1" fill="{fill}" stroke="{color}" stroke-width="1.5"/>'
        marks.append(f"<g>{shape}<title>{text(tip)}</title></g>")
    return "".join(marks)


def series(block):
    if not block.series:
        return ""
    groups = defaultdict(list)
    for item in block.series:
        groups[(item.get("period", 1), item.get("group", "value"))].append(item)
    figures = []
    periods = sorted({k[0] for k in groups})
    high = max(float(i["value"]) for i in block.series)
    low = min(0, min(float(i["value"]) for i in block.series))
    span = high - low or 1
    for period in periods:
        marks, labels = [], []
        items_period = [i for i in block.series if i.get("period", 1) == period]
        end = max(i["time_ms"] for i in items_period) or 1
        if block.markers:
            end = max(
                [end] + [m["time_ms"] for m in block.markers if m["period"] == period]
            )
        for tick in range(5):
            y = 180 - tick * 35
            value = low + span * tick / 4
            marks.append(
                f'<path d="M48 {y}H650" stroke="#d8e0da" stroke-dasharray="3 4"/><text x="7" y="{y + 4}">{numeric(value)}</text>'
            )
        for (p, group), items in groups.items():
            if p != period:
                continue
            identity = team(block, items[0].get("team_id"))
            color = identity["color"]
            labels.append(
                (
                    color,
                    identity["name"]
                    if items[0].get("team_id") is not None
                    else "Total de los equipos incluidos"
                    if block.insight_id == "xg_story"
                    else str(group),
                )
            )
            previous = (48, 180 + 140 * low / span)
            path = f"M{previous[0]} {previous[1]}"
            for item in sorted(items, key=lambda i: i["time_ms"]):
                x, y = (
                    48 + 600 * item["time_ms"] / end,
                    180 - 140 * (item["value"] - low) / span,
                )
                if block.insight_id == "xg_story":
                    path += f"H{x:.3f}V{y:.3f}"
                elif block.insight_id == "match_timeline":
                    path += f"L{x:.3f} {y:.3f}"
                marks.append(
                    f'<circle cx="{x:.3f}" cy="{y:.3f}" r="3.3" fill="{color}" stroke="#fff"><title>P{period} · {item["time_ms"] / 1000:g} s · {numeric(item["value"])}</title></circle>'
                )
            if block.insight_id in {"xg_story", "match_timeline"}:
                if block.insight_id == "xg_story":
                    path += "H648"
                marks.insert(
                    0,
                    f'<path d="{path}" stroke="{color}" stroke-width="2.5" fill="none"/>',
                )
        marks.append(
            f'<text x="48" y="210">0′</text><text x="608" y="210">{end / 60000:.1f}′</text><text x="48" y="20">P{period} · {text(block.unit or "valor observado")}</text>'
        )
        caption = (
            "xG acumulado sólo dentro de este período; cada período comienza en cero. Escalones en cada tiro. Eje hasta la última acción incluida."
            if block.insight_id == "xg_story"
            else "Eventos registrados por equipo en tramos de 5 minutos; el último tramo del período puede ser parcial."
            if block.insight_id == "match_timeline"
            else "Muestras independientes; no se interpolan huecos ni se unen períodos."
        )
        height = 230
        if any(m["period"] == period for m in block.markers):
            marks.append(marker_marks(block, period, end))
            caption += " Bajo el eje: ● gol, ◆ cambio, ▮ tarjeta, en el color del equipo (una franja por equipo)."
            height = 258
        figures.append(
            f'<figure><svg class="series" viewBox="0 0 690 {height}" role="img" aria-label="{text(block.title)}">{"".join(marks)}</svg>{legend(labels)}<figcaption>{caption}</figcaption></figure>'
        )
    return "".join(figures)


def energy_composition(block):
    fields = [
        ("gradient_fraction", "Gradiente", "#2463bc"),
        ("curl_fraction", "Circulación local", "#bf402e"),
        ("harmonic_fraction", "Armónica", "#7752ac"),
    ]
    if not any(k in block.metrics for k, _, _ in fields):
        return ""
    shapes, labels, offset = [], [], 0
    for key, name, color in fields:
        value = block.metrics.get(key)
        if value is None:
            continue
        width = max(0, value) * 650
        shapes.append(
            f'<rect x="{20 + offset:.3f}" y="20" width="{width:.3f}" height="30" fill="{color}"><title>{name}: {value:.1%}</title></rect>'
        )
        labels.append((color, f"{name} · {value:.1%}"))
        offset += width
    return f'<figure><svg viewBox="0 0 690 70" role="img" aria-label="Composición de energía Hodge">{"".join(shapes)}</svg>{legend(labels)}<figcaption>Fracciones de energía del flujo neto en el complejo seleccionado; no porcentajes de posesión.</figcaption></figure>'
