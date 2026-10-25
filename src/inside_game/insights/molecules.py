"""Moléculas: lecturas, leyendas, avisos y tablas que comparten los organismos."""

import json
import re

from .atoms import numeric, text


def legend(items):
    """Color + texto: la identidad no depende únicamente del color."""
    return (
        '<ul class="chart-legend" aria-label="Leyenda">'
        + "".join(
            f'<li><span class="legend-key" style="background:{color}"></span>{text(label)}</li>'
            for color, label in dict.fromkeys(items)
        )
        + "</ul>"
        if items
        else ""
    )


def metric_reading(label, value, teams=None):
    label = re.sub(r"^(?:r\d+-)?q\d+\.", "", label)
    names = {
        "shots": "Tiros",
        "attempted_passes": "Pases intentados",
        "completed_passes": "Pases completados",
        "completion_rate": "Acierto de pase",
        "passes_with_geometry": "Pases con coordenadas",
        "density": "Densidad de conexiones",
        "components_weak": "Componentes conectados",
        "grid_m": "Tamaño de celda (m)",
        "total_player_seconds": "Ocupación (s·jugador)",
        "pitch_area_m2": "Superficie del campo (m²)",
        "area_sum_m2": "Suma de celdas (m²)",
        "maximum_edge_length_m": "Escala máxima (m)",
        "observed_line_breaks": "Pases que cruzan líneas",
        "mapped_line_breaks": "Pases situados en el mapa",
        "goals": "Goles",
        "shots_on_target": "Tiros a puerta",
        "xg": "xG",
        "xg_per_shot": "xG por tiro",
        "goals_minus_xg": "Goles menos xG",
        "conversion_rate": "Proporción de conversión",
        "on_target_rate": "Proporción a puerta",
        "heatmap_scale_max": "Máximo de escala térmica",
        "sample_time_ms": "Instante del período (ms)",
        "eligible_passes": "Pases elegibles",
        "computed_passes": "Pases calculados",
        "supplied_frames": "Snapshots suministrados",
        "comparable_pairs": "Pares comparables",
        "events_in_supplied_evidence": "Eventos en la evidencia",
        "observed_xg": "xG observado",
        "observations": "Muestras",
        "period": "Período",
        "players": "Jugadores de campo",
        "width_m": "Anchura (m)",
        "length_m": "Longitud (m)",
        "radius_of_gyration_m": "Radio de giro (m)",
        "hull_area_m2": "Área de envolvente (m²)",
        "hull_perimeter_m": "Perímetro (m)",
        "component_count": "Componentes",
        "largest_component_fraction": "Fracción del componente mayor",
        "critical_connection_distance_m": "Distancia de conexión crítica (m)",
        "defensive_line_height_m": "Altura defensiva (m)",
        "observed_outfield_length_m": "Longitud observada (m)",
        "goalkeeper_height_m": "Altura del portero (m)",
        "longitudinal_gap_m": "Distancia portero-línea (m)",
        "reachable_players": "Jugadores conectados al balón",
        "observed_sequences": "Secuencias observadas",
        "gradient_fraction": "Fracción de gradiente",
        "curl_fraction": "Fracción de curl",
        "harmonic_fraction": "Fracción armónica",
        "net_flow_energy": "Energía del flujo neto",
        "reconstruction_error": "Error de reconstrucción",
        "orthogonality_error": "Error de ortogonalidad",
    }
    display = numeric(value)
    if label.endswith(("_rate", "_fraction")) and type(value) in (int, float):
        display = f"{value:.1%}"
    if label.startswith("team_area_m2."):
        key = label.split(".")[-1]
        label = (
            f"Área de {(teams or {}).get(key, {}).get('name', 'equipo ' + key)} (m²)"
        )
    else:
        label = names.get(label, label.replace("_", " "))
    return f'<div class="reading"><dt>{text(label)}</dt><dd>{display}</dd></div>'


def metrics(values, teams=None):
    if not values:
        return ""
    diagnostic = {
        "heatmap_scale_max",
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
        '<details class="metric-details"><summary>Más métricas y diagnóstico</summary><dl class="metrics">'
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
        '<details class="source-notes"><summary>Procedencia y límites</summary><ul>'
        + "".join(f"<li>{text(w)}</li>" for w in items)
        + "</ul></details>"
    )


def evidence_links(ids):
    return (
        '<p class="evidence-links">Evidencia: '
        + ", ".join(f'<a href="#evidence-{text(e)}">{text(e)}</a>' for e in ids)
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

    heading = "".join(f'<th scope="col">{text(k)}</th>' for k in keys)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell(row.get(k))}</td>" for k in keys) + "</tr>"
        for row in rows[:100]
    )
    return f'<details class="data-table"><summary>Tabla de datos · {len(rows)} filas</summary><div class="table-scroll"><table><thead><tr>{heading}</tr></thead><tbody>{body}</tbody></table></div><p class="muted">Vista de hasta 100 filas y 8 columnas. Datos completos en el JSON incluido.</p></details>'
