"""Contexto visual compartido por todas las piezas, incluido el replay.

La fuente no publica colores oficiales de los equipos anonimizados. La paleta
es configuración de presentación, resuelta una vez para todo el documento.
"""

PALETTE = ("#2463bc", "#bf402e", "#7752ac", "#13796d", "#a05c13", "#965475")


def identities(spec):
    teams, players = {}, {}
    for evidence in spec.evidence:
        if evidence.operation != "get_match_context":
            continue
        data = evidence.response.data
        match = data.get("match", {})
        for side in ("home", "away"):
            key = match.get(f"{side}_team_id")
            if key is not None:
                teams[str(key)] = {
                    "name": match.get(f"{side}_team_name") or f"Equipo {key}"
                }
        for player in data.get("lineups", []):
            players[str(player["player_id"])] = {
                "name": player.get("player_name") or str(player["player_id"]),
                "number": player.get("jersey_number"),
                "team_id": player.get("team_id"),
            }
    # Stable by ID, not by which teams happen to appear in a particular block.
    for key, value in teams.items():
        value["color"] = PALETTE[(int(key) - 1) % len(PALETTE)]
    for style in spec.teams:
        previous = teams.get(str(style.team_id), {})
        teams[str(style.team_id)] = {
            "name": style.name or previous.get("name", f"Equipo {style.team_id}"),
            "color": style.color,
        }
    return teams, players


def team(block, key):
    key = str(key)
    return block.teams.get(
        key,
        {
            "name": f"Equipo {key}" if key != "None" else "Sin equipo",
            "color": PALETTE[(int(key) - 1) % len(PALETTE)]
            if key.isdigit()
            else "#52675f",
        },
    )


def player_label(block, key):
    player = block.players.get(str(key), {})
    return str(player.get("number") if player.get("number") is not None else key or "")
