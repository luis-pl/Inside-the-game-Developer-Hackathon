"""Paquetes de recetas por plantilla del renderer.

`match` = una pieza del partido completo; `both` = una por equipo; `focus` = sólo
el equipo protagonista. El orden es el de lectura en la página.
"""

PACKAGES = {
    "match_overview": [
        ("shot_map", "match"),
        ("xg_story", "match"),
        ("match_timeline", "match"),
        ("entity_comparison", "match"),
        ("passing_network", "both"),
        ("final_third_channels", "both"),
        ("defensive_actions", "match"),
        ("team_shape", "focus"),
    ],
    "player_dossier": [
        ("movement_profile", "focus"),
        ("occupation_heatmap", "focus"),
        ("pass_map", "focus"),
        ("shot_map", "match"),
        ("ball_progression", "match"),
        ("defensive_actions", "match"),
        ("zone_presence", "focus"),
    ],
    "entity_comparison": [
        ("entity_comparison", "match"),
        ("passing_network", "both"),
        ("movement_profile", "both"),
        ("occupation_heatmap", "both"),
    ],
    "tactical_episode": [
        ("play_replay", "match"),
        ("team_shape", "focus"),
        ("space_partition", "match"),
        ("proximity_network", "focus"),
        ("defensive_line_height", "focus"),
        ("clearance_connectivity", "focus"),
        ("structural_pass", "focus"),
        ("between_lines_receptions", "focus"),
    ],
}

# Recetas de todo el partido cuando aparecen en un informe libre.
MATCH_LEVEL = {
    "shot_map",
    "xg_story",
    "match_timeline",
    "sequence_explorer",
    "defensive_actions",
    "pressure_recovery",
    "ball_progression",
    "entity_comparison",
    "play_replay",
    "space_partition",
}


# Piezas de partido que admiten filtro de equipo: si el usuario nombró un equipo
# ("¿desde dónde remató el Equipo B?"), se muestran sólo para ese equipo.
TEAM_FILTERABLE = {
    "shot_map",
    "xg_story",
    "defensive_actions",
    "pressure_recovery",
    "ball_progression",
}


def expand(intent):
    """Lista de (insight_id, alcance) para la intención."""
    if intent.template_id == "custom_report":
        return [
            (
                key,
                "match"
                if key in MATCH_LEVEL
                and not (intent.team_id and key in TEAM_FILTERABLE)
                else "focus",
            )
            for key in dict.fromkeys(intent.insight_ids)
        ]
    return PACKAGES[intent.template_id]
