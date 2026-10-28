"""Readable English names de las métricas y categorías que entrega la API.

Las claves de la API son técnicas (`tackles_won`, `outcomes.Off T`,
`event_counts.Ball Recovery`); lo que ve una persona debe leerse sin conocerlas.
"""

import re

METRIC_NAMES = {
    "shots": "Shots",
    "attempted_passes": "Attempted passes",
    "completed_passes": "Completed passes",
    "completion_rate": "Pass completion",
    "passes_with_geometry": "Passes with coordinates",
    "progressive_passes": "Progressive passes",
    "final_third_entries": "Final-third entries",
    "total_pass_length_m": "Total pass length (m)",
    "progressive_passes_with_geometry": "Progressive passes (with coordinates)",
    "final_third_entries_with_geometry": "Final-third entries (with coordinates)",
    "total_pass_length_with_geometry_m": "Pass length (m, with coordinates)",
    "cross": "Crosses",
    "cut_back": "Cutbacks",
    "switch": "Switches of play",
    "density": "Connection density",
    "components_weak": "Connected components",
    "grid_m": "Cell size (m)",
    "total_player_seconds": "Occupation (player·s)",
    "valid_player_seconds": "Valid player seconds",
    "player_seconds_in_zone": "Player seconds in the zone",
    "sampled_entries": "Sampled entries",
    "pitch_area_m2": "Pitch area (m²)",
    "area_sum_m2": "Combined cell area (m²)",
    "maximum_edge_length_m": "Maximum scale (m)",
    "observed_line_breaks": "Line-breaking passes",
    "mapped_line_breaks": "Passes mapped",
    "goals": "Goals",
    "shots_on_target": "Shots on target",
    "xg": "xG",
    "xg_per_shot": "xG per shot",
    "goals_minus_xg": "Goals minus xG",
    "conversion_rate": "Conversion rate",
    "on_target_rate": "On-target rate",
    "heatmap_scale_max": "Heat scale maximum",
    "sample_time_ms": "Period time (ms)",
    "eligible_passes": "Eligible passes",
    "computed_passes": "Evaluated passes",
    "supplied_frames": "Supplied snapshots",
    "comparable_pairs": "Comparable pairs",
    "events_in_supplied_evidence": "Events in evidence",
    "observed_xg": "Total xG of included shots",
    "observations": "Samples",
    "period": "Period",
    "players": "Outfield players",
    "width_m": "Width (m)",
    "length_m": "Length (m)",
    "radius_of_gyration_m": "Radius of gyration (m)",
    "hull_area_m2": "Convex hull area (m²)",
    "hull_perimeter_m": "Perimeter (m)",
    "component_count": "Components",
    "largest_component_fraction": "Largest component fraction",
    "critical_connection_distance_m": "Critical connection distance (m)",
    "epsilon_m": "Connection distance (m)",
    "defensive_line_height_m": "Defensive line height (m)",
    "observed_outfield_length_m": "Observed outfield length (m)",
    "goalkeeper_height_m": "Goalkeeper height (m)",
    "longitudinal_gap_m": "Goalkeeper–line gap (m)",
    "reachable_players": "Players connected to the ball",
    "observed_sequences": "Observed sequences",
    "gradient_fraction": "Gradient fraction",
    "curl_fraction": "Local circulation fraction",
    "harmonic_fraction": "Harmonic fraction",
    "net_flow_energy": "Net flow energy",
    "reconstruction_error": "Reconstruction error",
    "orthogonality_error": "Orthogonality error",
    # Movimiento, espacio y estructura
    "bottleneck_radius_m": "Bottleneck radius (m)",
    "cell_x_m": "Cell x (m)",
    "cell_y_m": "Cell y (m)",
    "covered_seconds": "Covered seconds",
    "valid_seconds": "Valid seconds",
    "seconds_in_zone": "Seconds in zone",
    "seconds_above_5_5_m_s": "Seconds above 5.5 m/s",
    "max_sampled_speed_m_s": "Maximum sampled speed (m/s)",
    "distance_m": "Distance (m)",
    "full_width_m": "Full width (m)",
    "line_bypass_count": "Lines bypassed",
    "relative_space_gain": "Relative space gain",
    "snapshot_time_ms": "Instant (ms)",
    "entries": "Entries",
    "category": "Category",
    "path": "Path",
    "end_x": "Destination x",
    "end_y": "Destination y",
    # Acciones defensivas y con balón
    "tackle_attempts": "Attempted tackles",
    "tackles_won": "Tackles won",
    "tackles_lost": "Tackles lost",
    "aerial_contests": "Aerial duels",
    "aerial_won": "Aerial duels won",
    "aerial_lost": "Aerial duels lost",
    "fifty_fifty_winning_records": "50/50 contests won",
    "fifty_fifty_losing_records": "50/50 contests lost",
    "interceptions": "Interceptions",
    "pressures": "Pressures",
    "counterpressures": "Counterpressures",
    "blocks": "Blocks",
    "clearances": "Clearances",
    "recoveries": "Recoveries",
    "fouls_committed": "Fouls committed",
    "dribble_attempts": "Attempted dribbles",
    "dribbles_complete": "Completed dribbles",
    "dribbles_incomplete": "Unsuccessful dribbles",
    "dribble_success_rate": "Dribble success rate",
    "carries": "Carries",
    "carry_seconds": "Carry time (s)",
    "carry_displacement_m": "Carry displacement (m)",
    "carry_progression_m": "Carry progression (m)",
    "miscontrols": "Miscontrols",
    "dispossessed": "Dispossessions",
    "receipts": "Receptions",
}

OUTCOMES = {
    "Goal": "Goal",
    "Saved": "Saved",
    "Saved to Post": "Saved onto post",
    "Off T": "Off target",
    "Blocked": "Blocked",
    "Post": "Woodwork",
    "Wayward": "Wayward",
}
BODY_PARTS = {
    "Head": "Head",
    "Left Foot": "Left foot",
    "Right Foot": "Right foot",
    "Other": "Other",
}
EVENT_TYPES = {
    "Pass": "Passes",
    "Shot": "Shots",
    "Carry": "Carries",
    "Dribble": "Dribbles",
    "Dribbled Past": "Dribbled past",
    "Duel": "Duels",
    "50/50": "50/50 contests",
    "Pressure": "Pressures",
    "Interception": "Interceptions",
    "Clearance": "Clearances",
    "Block": "Blocks",
    "Ball Recovery": "Recoveries",
    "Recovery": "Recoveries",
    "Goal Keeper": "Goalkeeper actions",
    "Ball Receipt*": "Receptions",
    "Ball Out": "Ball out",
    "Dispossessed": "Dispossessions",
    "Miscontrol": "Miscontrols",
    "Foul Committed": "Fouls committed",
    "Foul Won": "Fouls won",
    "Metrica Ball Lost": "Balls lost",
    "Metrica Challenge": "Challenges",
    "SkillCorner off_ball_run": "Off-ball runs",
    "SkillCorner on_ball_engagement": "On-ball pressure",
    "SkillCorner passing_option": "Passing options",
    "SkillCorner player_possession": "Player possessions",
}
# Carril 1…5 de ancho: sólo se nombra el tipo, no el lado, porque el sentido de
# la coordenada depende de la convención de cada fuente.
LANES = {1: "wide", 2: "half-space", 3: "central", 4: "half-space", 5: "wide"}


def clean_key(key):
    """Sin prefijos de transporte (`aN-`, `rN-`), de consulta (`qN.`) ni de agregado."""
    key = re.sub(r"^(?:(?:(?:r|a)\d+|data-[0-9a-f]{32})-)*q\d+\.", "", str(key))
    return re.sub(r"^(?:summary|aggregate)\.", "", key)


def metric_label(key, teams=None):
    key = clean_key(key)
    if key.startswith("team_area_m2."):
        team = key.split(".")[-1]
        name = (teams or {}).get(team, {}).get("name", "team " + team)
        return f"Area of {name} (m²)"
    if key.startswith("baseline."):
        return "Baseline: " + metric_label(key[len("baseline.") :], teams)
    lane = re.fullmatch(r"channel_(\d)", key)
    if lane:
        n = int(lane.group(1))
        return f"Channel {n} ({LANES.get(n, 'channel')})"
    for prefix, label, names in (
        ("outcomes.", "Outcome", OUTCOMES),
        ("body_parts.", "Body part", BODY_PARTS),
    ):
        if key.startswith(prefix):
            value = key[len(prefix) :]
            return f"{label}: {names.get(value, value)}"
    if key.startswith("event_counts."):
        value = key[len("event_counts.") :]
        return f"Events · {EVENT_TYPES.get(value, value)}"
    return METRIC_NAMES.get(key, key.replace("_", " ").replace(".", " · "))


COLUMN_NAMES = {
    "event_id": "Event ID",
    "event_index": "Event number",
    "match_id": "Match",
    "period": "Period",
    "time_ms": "Time (ms)",
    "start_ms": "Start (ms)",
    "end_ms": "End (ms)",
    "period_time_ms": "Period time (ms)",
    "timestamp": "Timestamp",
    "minute": "Minute",
    "second": "Second",
    "type": "Type",
    "type_id": "Type ID",
    "type_name": "Type",
    "player": "Player",
    "player_id": "Player ID",
    "player_name": "Player",
    "team_id": "Team ID",
    "entity_id": "Entity",
    "source": "Source",
    "target": "Target",
    "passes": "Passes",
    "channel": "Channel",
    "matches": "Matches",
    "aggregate": "Aggregate",
    "x": "x (m)",
    "y": "y (m)",
    "value": "Value",
    "label": "Label",
}


def column_label(key):
    """Encabezado de una tabla de datos: nombre conocido o la clave legible."""
    key = str(key)
    return COLUMN_NAMES.get(key) or (
        metric_label(key) if key in METRIC_NAMES else key.replace("_", " ")
    )
