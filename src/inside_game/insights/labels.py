"""Nombres legibles en español de las métricas y categorías que entrega la API.

Las claves de la API son técnicas (`tackles_won`, `outcomes.Off T`,
`event_counts.Ball Recovery`); lo que ve una persona debe leerse sin conocerlas.
"""

import re

METRIC_NAMES = {
    "shots": "Tiros",
    "attempted_passes": "Pases intentados",
    "completed_passes": "Pases completados",
    "completion_rate": "Acierto de pase",
    "passes_with_geometry": "Pases con coordenadas",
    "progressive_passes": "Pases progresivos",
    "final_third_entries": "Entradas al último tercio",
    "total_pass_length_m": "Longitud total de pases (m)",
    "progressive_passes_with_geometry": "Pases progresivos (sólo con coordenadas)",
    "final_third_entries_with_geometry": "Entradas al último tercio (sólo con coordenadas)",
    "total_pass_length_with_geometry_m": "Longitud de pases (m, sólo con coordenadas)",
    "cross": "Centros",
    "cut_back": "Pases atrás desde la línea de fondo",
    "switch": "Cambios de orientación",
    "density": "Densidad de conexiones",
    "components_weak": "Componentes conectados",
    "grid_m": "Tamaño de celda (m)",
    "total_player_seconds": "Ocupación (s·jugador)",
    "valid_player_seconds": "Segundos-jugador válidos",
    "player_seconds_in_zone": "Segundos-jugador en la zona",
    "sampled_entries": "Entradas muestreadas",
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
    "epsilon_m": "Distancia de conexión (m)",
    "defensive_line_height_m": "Altura defensiva (m)",
    "observed_outfield_length_m": "Longitud observada (m)",
    "goalkeeper_height_m": "Altura del portero (m)",
    "longitudinal_gap_m": "Distancia portero-línea (m)",
    "reachable_players": "Jugadores conectados al balón",
    "observed_sequences": "Secuencias observadas",
    "gradient_fraction": "Fracción de gradiente",
    "curl_fraction": "Fracción de circulación local",
    "harmonic_fraction": "Fracción armónica",
    "net_flow_energy": "Energía del flujo neto",
    "reconstruction_error": "Error de reconstrucción",
    "orthogonality_error": "Error de ortogonalidad",
    # Movimiento, espacio y estructura
    "bottleneck_radius_m": "Radio del cuello de botella (m)",
    "cell_x_m": "Celda x (m)",
    "cell_y_m": "Celda y (m)",
    "covered_seconds": "Segundos cubiertos",
    "valid_seconds": "Segundos válidos",
    "seconds_in_zone": "Segundos en la zona",
    "seconds_above_5_5_m_s": "Segundos por encima de 5,5 m/s",
    "max_sampled_speed_m_s": "Velocidad máxima muestreada (m/s)",
    "distance_m": "Distancia (m)",
    "full_width_m": "Anchura completa (m)",
    "line_bypass_count": "Líneas superadas",
    "relative_space_gain": "Ganancia relativa de espacio",
    "snapshot_time_ms": "Instante (ms)",
    "entries": "Entradas",
    "category": "Categoría",
    "path": "Trayectoria",
    "end_x": "Destino x",
    "end_y": "Destino y",
    # Acciones defensivas y con balón
    "tackle_attempts": "Entradas intentadas",
    "tackles_won": "Entradas ganadas",
    "tackles_lost": "Entradas perdidas",
    "aerial_contests": "Duelos aéreos",
    "aerial_won": "Duelos aéreos ganados",
    "aerial_lost": "Duelos aéreos perdidos",
    "fifty_fifty_winning_records": "Disputas 50/50 ganadas",
    "fifty_fifty_losing_records": "Disputas 50/50 perdidas",
    "interceptions": "Intercepciones",
    "pressures": "Presiones",
    "counterpressures": "Contrapresiones",
    "blocks": "Bloqueos",
    "clearances": "Despejes",
    "recoveries": "Recuperaciones",
    "fouls_committed": "Faltas cometidas",
    "dribble_attempts": "Regates intentados",
    "dribbles_complete": "Regates completados",
    "dribbles_incomplete": "Regates fallidos",
    "dribble_success_rate": "Acierto de regate",
    "carries": "Conducciones",
    "carry_seconds": "Tiempo conduciendo (s)",
    "carry_displacement_m": "Desplazamiento conduciendo (m)",
    "carry_progression_m": "Progresión conduciendo (m)",
    "miscontrols": "Controles fallidos",
    "dispossessed": "Pérdidas por despojo",
    "receipts": "Recepciones",
}

OUTCOMES = {
    "Goal": "Gol",
    "Saved": "Parado",
    "Saved to Post": "Parado al poste",
    "Off T": "Fuera",
    "Blocked": "Bloqueado",
    "Post": "Poste",
    "Wayward": "Desviado",
}
BODY_PARTS = {
    "Head": "Cabeza",
    "Left Foot": "Pie izquierdo",
    "Right Foot": "Pie derecho",
    "Other": "Otra parte",
}
EVENT_TYPES = {
    "Pass": "Pases",
    "Shot": "Tiros",
    "Carry": "Conducciones",
    "Dribble": "Regates",
    "Dribbled Past": "Regateado por el rival",
    "Duel": "Duelos",
    "50/50": "Disputas 50/50",
    "Pressure": "Presiones",
    "Interception": "Intercepciones",
    "Clearance": "Despejes",
    "Block": "Bloqueos",
    "Ball Recovery": "Recuperaciones",
    "Recovery": "Recuperaciones",
    "Goal Keeper": "Acciones de portero",
    "Ball Receipt*": "Recepciones",
    "Ball Out": "Balón fuera",
    "Dispossessed": "Despojos",
    "Miscontrol": "Controles fallidos",
    "Foul Committed": "Faltas cometidas",
    "Foul Won": "Faltas recibidas",
    "Metrica Ball Lost": "Balones perdidos",
    "Metrica Challenge": "Disputas",
    "SkillCorner off_ball_run": "Desmarques sin balón",
    "SkillCorner on_ball_engagement": "Presión sobre el poseedor",
    "SkillCorner passing_option": "Opciones de pase",
    "SkillCorner player_possession": "Posesiones de jugador",
}
# Carril 1…5 de ancho: sólo se nombra el tipo, no el lado, porque el sentido de
# la coordenada depende de la convención de cada fuente.
LANES = {1: "banda", 2: "interior", 3: "centro", 4: "interior", 5: "banda"}


def clean_key(key):
    """Sin prefijos de transporte (`aN-`, `rN-`), de consulta (`qN.`) ni de agregado."""
    key = re.sub(r"^(?:(?:r|a)\d+-)*q\d+\.", "", str(key))
    return re.sub(r"^(?:summary|aggregate)\.", "", key)


def metric_label(key, teams=None):
    key = clean_key(key)
    if key.startswith("team_area_m2."):
        team = key.split(".")[-1]
        name = (teams or {}).get(team, {}).get("name", "equipo " + team)
        return f"Área de {name} (m²)"
    if key.startswith("baseline."):
        return "Referencia: " + metric_label(key[len("baseline.") :], teams)
    lane = re.fullmatch(r"channel_(\d)", key)
    if lane:
        n = int(lane.group(1))
        return f"Carril {n} ({LANES.get(n, 'carril')})"
    for prefix, label, names in (
        ("outcomes.", "Resultado", OUTCOMES),
        ("body_parts.", "Parte del cuerpo", BODY_PARTS),
    ):
        if key.startswith(prefix):
            value = key[len(prefix) :]
            return f"{label}: {names.get(value, value)}"
    if key.startswith("event_counts."):
        value = key[len("event_counts.") :]
        return f"Eventos · {EVENT_TYPES.get(value, value)}"
    return METRIC_NAMES.get(key, key.replace("_", " ").replace(".", " · "))


COLUMN_NAMES = {
    "event_id": "ID del evento",
    "event_index": "N.º de evento",
    "match_id": "Partido",
    "period": "Período",
    "time_ms": "Tiempo (ms)",
    "start_ms": "Inicio (ms)",
    "end_ms": "Fin (ms)",
    "period_time_ms": "Tiempo del período (ms)",
    "timestamp": "Marca de tiempo",
    "minute": "Minuto",
    "second": "Segundo",
    "type": "Tipo",
    "type_id": "ID del tipo",
    "type_name": "Tipo",
    "player": "Jugador",
    "player_id": "Jugador (ID)",
    "player_name": "Jugador",
    "team_id": "Equipo (ID)",
    "entity_id": "Entidad",
    "source": "Origen",
    "target": "Destino",
    "passes": "Pases",
    "channel": "Carril",
    "matches": "Partidos",
    "aggregate": "Agregado",
    "x": "x (m)",
    "y": "y (m)",
    "value": "Valor",
    "label": "Etiqueta",
}


def column_label(key):
    """Encabezado de una tabla de datos: nombre conocido o la clave legible."""
    key = str(key)
    return COLUMN_NAMES.get(key) or (
        metric_label(key) if key in METRIC_NAMES else key.replace("_", " ")
    )
