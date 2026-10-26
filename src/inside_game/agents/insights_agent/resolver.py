"""Intención → consultas exactas y bloques. Determinista: no usa LLM.

Decide lo que el usuario no dice y la matriz de disponibilidad demostró
necesario: orientación y roles anotados por la fuente (nunca por dorsal),
instante con cobertura completa, ventanas ancladas en pases y límites en
instantes muestreados. Lo que la fuente no puede mostrar se descarta con motivo.

`fetch(operation, arguments)` es asíncrono y devuelve `(páginas, error)`: las
páginas son evidencias originales (dict) y `error` un texto o None. Sólo se usa
para el contexto y las sondas; las consultas de los bloques se devuelven en el
plan para que las ejecute el cliente de datos.
"""

import json
from math import hypot

from inside_game.insights.catalog import RECIPES
from inside_game.service import OPERATIONS

from .contracts import (
    BlockPlan,
    Discarded,
    InsightIntent,
    PlanLabels,
    QuerySpec,
    ResolvedPlan,
)
from .profiles import load_profiles, source_key
from .templates import expand

# Instantes candidatos si el usuario no da uno; SkillCorner (broadcast) deja
# jugadores fuera de cámara y el análisis espacial exige a todos los activos.
CANDIDATE_TIMES_MS = [
    600000,
    900000,
    1200000,
    300000,
    1500000,
    1800000,
    2100000,
    2400000,
]
# Alrededor de un instante pedido por el usuario.
NEARBY_OFFSETS_MS = [0, 5000, -5000, 10000, -10000, 30000, -30000, 60000, -60000]
EPISODE_HALF_MS = 10000
# Momentos candidatos (goles / tiros) que se prueban hasta hallar uno con cobertura.
KEY_MOMENTS = 5
PASS_WINDOW_MS = 60000
MIN_PASSES_IN_WINDOW = 3
# Tracking a 1 s en fuentes reales: el frame más cercano está a ≤500 ms.
PASS_TRACKING_TOLERANCE_MS = 500

# Necesitan un instante con todos los participantes posicionados.
SNAPSHOT = {
    "team_shape",
    "proximity_network",
    "space_partition",
    "persistent_structure",
    "node_robustness",
    "clearance_connectivity",
    "defensive_line_height",
    "goalkeeper_connection",
}
# Piezas de la ficha que no describen a un portero (saldrían casi siempre en cero).
OUTFIELD_ONLY = {"shot_map", "ball_progression", "defensive_actions"}
PASS_TRACKING = {"structural_pass", "between_lines_receptions"}
ORIENTED = PASS_TRACKING | {"defensive_line_height", "goalkeeper_connection"}


def second(ms):
    """La API exige límites de tracking en instantes muestreados."""
    return ms // 1000 * 1000


def clock_minutes(clock):
    mm, ss = clock.split(":")
    return int(mm) + float(ss) / 60


def source_roles(context, team_id, period, time_ms):
    """Roles según las posiciones anotadas por la fuente en ese instante."""
    at = time_ms / 60000 + (45 if period == 2 else 0)
    roles = {"defender_ids": [], "midfielder_ids": [], "goalkeeper_id": None}
    for row in context.get("position_intervals", []):
        position = row.get("position") or ""
        if (
            row["team_id"] != team_id
            or not row["from_period"] <= period <= row["to_period"]
        ):
            continue
        if not clock_minutes(row["from_time"]) <= at < clock_minutes(row["to_time"]):
            continue
        if position == "Goalkeeper":
            roles["goalkeeper_id"] = row["player_id"]
        elif "Back" in position:
            roles["defender_ids"].append(row["player_id"])
        elif "Midfield" in position:
            roles["midfielder_ids"].append(row["player_id"])
    return {k: v for k, v in roles.items() if v}


def orientation(context, team_id, period):
    match = context["match"]
    row = next((p for p in context.get("periods", []) if p["period"] == period), None)
    home_positive = (row or {}).get("home_attacks_positive_x")
    if home_positive is None:
        return None
    return home_positive if team_id == match["home_team_id"] else not home_positive


def period_duration_ms(context, period):
    row = next((p for p in context.get("periods", []) if p["period"] == period), None)
    return (row or {}).get("duration_ms") or 45 * 60000


def player_label(row):
    return (
        row.get("player_nickname")
        or row.get("player_name")
        or f"jugador {row['player_id']}"
    )


def missing_roles(insight_id, own, rival):
    if insight_id == "defensive_line_height" and not own.get("defender_ids"):
        return (
            "La fuente no anota defensores de este equipo; no se infieren por dorsal."
        )
    if insight_id == "goalkeeper_connection" and not (
        own.get("defender_ids") and own.get("goalkeeper_id")
    ):
        return "La fuente no anota portero y defensores de este equipo."
    if insight_id == "between_lines_receptions" and not (
        rival.get("defender_ids") and rival.get("midfielder_ids")
    ):
        return "La fuente no anota defensores y medios del rival; no se infieren por dorsal."
    return None


class _Plan:
    """Consultas deduplicadas por (operación, argumentos validados)."""

    def __init__(self):
        self.queries, self.keys = [], {}

    def add(self, operation, arguments):
        checked = (
            OPERATIONS[operation].model_validate(arguments).model_dump(mode="json")
        )
        identity = operation + json.dumps(checked, sort_keys=True)
        if identity not in self.keys:
            key = f"q{len(self.queries) + 1}"
            self.keys[identity] = key
            self.queries.append(
                QuerySpec(key=key, operation=operation, arguments=checked)
            )
        return self.keys[identity]


class Resolver:
    def __init__(self, fetch, *, profiles=None, apply_profile=True):
        self.fetch = fetch
        self.profiles = load_profiles() if profiles is None else profiles
        self.apply_profile = apply_profile

    async def resolve(self, intent: InsightIntent | dict) -> ResolvedPlan:
        intent = InsightIntent.model_validate(intent)
        pages, error = await self.fetch(
            "get_match_context", {"match_id": intent.match_id}
        )
        if error or not pages:
            raise ValueError(f"MATCH_CONTEXT_UNAVAILABLE: {error}")
        context = pages[0]["response"]["data"]
        match = context["match"]
        home, away = match["home_team_id"], match["away_team_id"]
        names = {home: match["home_team_name"], away: match["away_team_name"]}
        if intent.team_id is not None and intent.team_id not in names:
            raise ValueError("TEAM_NOT_IN_MATCH")
        players = {
            row["player_id"]: row
            for row in context.get("lineups", [])
            if row.get("player_id") is not None
        }
        if intent.player_id is not None and intent.player_id not in players:
            raise ValueError("PLAYER_NOT_IN_MATCH")
        # La ficha de un jugador se centra en su equipo. Si la intención trae un
        # equipo distinto (por ejemplo, arrastrado de un seguimiento), el equipo
        # del jugador manda y el ajuste queda explícito en `decisions`.
        requested_team = intent.team_id
        player_team = (
            players[intent.player_id].get("team_id") if intent.player_id else None
        )
        adjusted_from = None
        if (
            player_team is not None
            and requested_team is not None
            and requested_team != player_team
        ):
            adjusted_from = requested_team
            intent = intent.model_copy(update={"team_id": player_team})
        focus = intent.team_id or player_team or home
        source = source_key(match)
        profile = self.profiles.get(source, {}) if self.apply_profile else {}
        decisions = {
            "source": source,
            "focus_team": "equipo del jugador (ajustado)"
            if adjusted_from is not None
            else "solicitado"
            if requested_team
            else "equipo del jugador"
            if intent.player_id
            else "local por defecto",
            "profile_measured_on": profile.get("measured_match_id"),
        }
        if adjusted_from is not None:
            decisions["team_adjusted_from"] = adjusted_from
        if self.apply_profile and not profile:
            decisions["profile"] = "Fuente sin perfil medido; no se filtra por fuente."

        entries, discarded = [], []
        for insight_id, reach in expand(intent):
            teams = {"match": [None], "focus": [focus], "both": [home, away]}[reach]
            for team_id in teams:
                reason = (profile.get("unavailable") or {}).get(insight_id) or (
                    profile.get("zero_only") or {}
                ).get(insight_id)
                if reason:
                    discarded.append(
                        Discarded(insight_id=insight_id, team_id=team_id, reason=reason)
                    )
                else:
                    entries.append((insight_id, team_id))

        period = intent.period or 1
        keys = {k for k, _ in entries}
        time_ms = second(intent.time_ms) if intent.time_ms is not None else None
        if keys & SNAPSHOT:
            found = None
            # Sin instante pedido, un episodio táctico se ancla en un momento del
            # partido (gol o tiro peligroso del equipo), no en una hora fija.
            if intent.template_id == "tactical_episode" and time_ms is None:
                for m_period, m_time, why in await self._key_moments(intent, focus):
                    found = await self._covered_instant(
                        intent, focus, m_period, second(m_time), context
                    )
                    if found is not None:
                        period, time_ms = m_period, found
                        decisions["moment"] = why
                        if found != second(m_time):
                            decisions["moment_ms"] = second(m_time)
                        break
            if found is None:
                found = await self._covered_instant(
                    intent, focus, period, time_ms, context
                )
            if found is None:
                for k, t in [e for e in entries if e[0] in SNAPSHOT]:
                    discarded.append(
                        Discarded(
                            insight_id=k,
                            team_id=t,
                            reason="Ningún instante cercano tiene a todos los participantes posicionados.",
                        )
                    )
                entries = [e for e in entries if e[0] not in SNAPSHOT]
            elif "moment" not in decisions:
                if time_ms is not None and found != time_ms:
                    decisions["instant_adjusted_from_ms"] = time_ms
                time_ms = found
        if time_ms is None:
            time_ms = CANDIDATE_TIMES_MS[0]
        decisions.update(period=period, time_ms=time_ms)

        roles = {t: source_roles(context, t, period, time_ms) for t in (home, away)}
        orient = {t: orientation(context, t, period) for t in (home, away)}
        decisions["roles"] = "posiciones anotadas por la fuente en el instante"
        decisions["roles_by_team"] = {str(t): r for t, r in roles.items()}
        decisions["attack_positive_x"] = {str(t): o for t, o in orient.items()}

        keeper = roles[focus].get("goalkeeper_id")
        if (
            intent.template_id == "player_dossier"
            and intent.player_id is not None
            and keeper == intent.player_id
        ):
            for insight_id, team_id in [e for e in entries if e[0] in OUTFIELD_ONLY]:
                discarded.append(
                    Discarded(
                        insight_id=insight_id,
                        team_id=team_id,
                        reason="El jugador es el portero según la fuente: esta pieza describe acciones de jugadores de campo.",
                    )
                )
            entries = [e for e in entries if e[0] not in OUTFIELD_ONLY]

        kept = []
        for insight_id, team_id in entries:
            team = team_id or focus
            other = away if team == home else home
            reason = None
            if insight_id in ORIENTED and orient[team] is None:
                reason = (
                    "La fuente no indica la orientación del ataque en este período."
                )
            reason = reason or missing_roles(insight_id, roles[team], roles[other])
            if reason:
                discarded.append(
                    Discarded(insight_id=insight_id, team_id=team_id, reason=reason)
                )
            else:
                kept.append((insight_id, team_id))
        entries = kept

        pass_windows = {}
        for team in {t or focus for k, t in entries if k in PASS_TRACKING}:
            pass_windows[team] = await self._pass_window(
                intent.match_id, team, period, time_ms
            )
        decisions["pass_windows"] = {str(t): w for t, w in pass_windows.items()}
        entries, no_passes = (
            [
                e
                for e in entries
                if e[0] not in PASS_TRACKING or pass_windows[e[1] or focus]
            ],
            [
                e
                for e in entries
                if e[0] in PASS_TRACKING and not pass_windows[e[1] or focus]
            ],
        )
        discarded += [
            Discarded(
                insight_id=k,
                team_id=t,
                reason="No hay tramo con pases completados suficientes del equipo.",
            )
            for k, t in no_passes
        ]

        scene = {
            "intent": intent,
            "home": home,
            "away": away,
            "focus": focus,
            "period": period,
            "time_ms": time_ms,
            "roles": roles,
            "orient": orient,
            "pass_windows": pass_windows,
        }
        plan, blocks = _Plan(), []
        for insight_id, team_id in entries:
            queries, parameters = build(
                insight_id, team_id or focus, team_id is None, scene
            )
            if intent.player_id:
                suffix = " · " + player_label(players[intent.player_id])
            else:
                suffix = f" · {names[team_id]}" if team_id else ""
            if insight_id in SNAPSHOT:
                # Una pieza de un instante lo dice en el título: no habla de todo el partido.
                seconds = time_ms // 1000
                suffix += f" · P{period} {seconds // 60:02d}:{seconds % 60:02d}"
            blocks.append(
                BlockPlan(
                    id=f"{insight_id}-{team_id}" if team_id else insight_id,
                    insight_id=insight_id,
                    title=RECIPES[insight_id]["title"] + suffix,
                    query_keys=list(dict.fromkeys(plan.add(o, a) for o, a in queries)),
                    parameters={k: v for k, v in parameters.items() if v is not None},
                )
            )
        return ResolvedPlan(
            intent=intent,
            source=source,
            labels=PlanLabels(
                match=f"{names[home]} vs {names[away]}",
                competition=match.get("competition_name"),
                home_team=names[home],
                away_team=names[away],
                focus_team=names[focus],
                player=player_label(players[intent.player_id])
                if intent.player_id
                else None,
                provider=match.get("provider"),
                data_kind=match.get("data_kind"),
                synthetic=bool(match.get("is_synthetic")),
            ),
            home_team_id=home,
            away_team_id=away,
            focus_team_id=focus,
            profile_measured=bool(profile.get("measured_match_id")),
            zero_only_insights=sorted(profile.get("zero_only") or {}),
            unannotated_metrics=profile.get("unannotated_metrics") or {},
            queries=plan.queries,
            blocks=blocks,
            discarded=discarded,
            decisions=decisions,
        )

    async def _key_moments(self, intent, team_id):
        """(período, ms, motivo) de los goles y tiros más peligrosos del equipo."""
        pages, error = await self.fetch(
            "get_shots", {"match_id": intent.match_id, "team_id": team_id, "limit": 200}
        )
        if error:
            return []
        shots = [
            e
            for page in pages
            for e in page["response"]["data"]["items"]
            if e.get("period") in (1, 2)
            and e.get("period_time_ms") is not None
            and (intent.period is None or e["period"] == intent.period)
        ]

        def goal_distance(e):
            """Metros hasta el centro de la portería rival (campo 105×68 m)."""
            x, y = e.get("attacking_x_m"), e.get("attacking_y_m")
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                return hypot(105 - x, 34 - y)
            return None

        def rank(e):
            shot = e.get("shot") or {}
            xg = shot.get("statsbomb_xg")
            goal = (shot.get("outcome") or {}).get("name") == "Goal"
            distance = goal_distance(e)
            return (
                not goal,
                -(xg if isinstance(xg, (int, float)) else 0),
                distance if distance is not None else float("inf"),
                e["period"],
                e["period_time_ms"],
            )

        moments = []
        for e in sorted(shots, key=rank)[:KEY_MOMENTS]:
            shot = e.get("shot") or {}
            if (shot.get("outcome") or {}).get("name") == "Goal":
                why = "gol del equipo protagonista"
            elif isinstance(shot.get("statsbomb_xg"), (int, float)):
                why = "tiro de mayor xG del equipo protagonista"
            elif goal_distance(e) is not None:
                why = "tiro más cercano a portería del equipo protagonista (la fuente no anota xG)"
            else:
                why = "tiro del equipo protagonista"
            moments.append((e["period"], e["period_time_ms"], why))
        return moments

    async def _covered_instant(self, intent, team_id, period, time_ms, context):
        duration = period_duration_ms(context, period)
        if time_ms is None:
            candidates = CANDIDATE_TIMES_MS
        else:
            candidates = [time_ms + o for o in NEARBY_OFFSETS_MS]
        for t in candidates:
            if not EPISODE_HALF_MS <= t <= duration - EPISODE_HALF_MS:
                continue
            _, error = await self.fetch(
                "get_team_shape",
                {
                    "match_id": intent.match_id,
                    "team_id": team_id,
                    "period": period,
                    "time_ms": t,
                    "view": "geometry",
                },
            )
            if not error:
                return t
        return None

    async def _pass_window(self, match_id, team_id, period, time_ms):
        """60 s anclados en pases completados del equipo desde el instante.

        Una ventana fija puede no contener pases (en el sintético, P1 9:50–10:10
        no tiene ninguno del local) y las recetas pase ↔ tracking quedan vacías.
        """
        pages, error = await self.fetch(
            "get_passes",
            {
                "match_id": match_id,
                "team_id": team_id,
                "scope": {"kind": "period", "period": period},
                "limit": 200,
            },
        )
        if error:
            return None
        times = sorted(
            e["period_time_ms"]
            for page in pages
            for e in page["response"]["data"]["items"]
            if (e.get("pass") or {}).get("outcome") is None
        )
        # Primero desde el instante elegido; si no, cualquier tramo del período.
        for pool in ([t for t in times if t >= time_ms - EPISODE_HALF_MS], times):
            for start in pool:
                if (
                    sum(start <= t < start + PASS_WINDOW_MS - 5000 for t in times)
                    >= MIN_PASSES_IN_WINDOW
                ):
                    start = second(start) - 5000
                    return {
                        "kind": "window",
                        "period": period,
                        "start_ms": max(start, 0),
                        "end_ms": max(start, 0) + PASS_WINDOW_MS,
                    }
        return None


def build(insight_id, team_id, match_level, scene):
    """Consultas y parámetros de una receta para un equipo."""
    intent = scene["intent"]
    m = {"match_id": intent.match_id}
    player = {"player_id": intent.player_id} if intent.player_id else {}
    scope = (
        {"kind": "period", "period": intent.period}
        if intent.period
        else {"kind": "match"}
    )
    in_scope = {"scope": scope}
    period = scene["period"]
    time_ms = scene["time_ms"]
    rival = scene["away"] if team_id == scene["home"] else scene["home"]
    team = {**m, "team_id": team_id}
    # Una pieza de partido completo no filtra equipo; en ficha de jugador, sí jugador.
    who = {**m, **player} if match_level else {**team, **player}
    p_who = player if match_level else {"team_id": team_id, **player}
    p_scope = {**p_who, "period": intent.period}
    episode = {
        "kind": "window",
        "period": period,
        "start_ms": time_ms - EPISODE_HALF_MS,
        "end_ms": time_ms + EPISODE_HALF_MS,
    }
    snapshot = {**team, "period": period, "time_ms": time_ms, "view": "geometry"}
    p_snap = {"team_id": team_id, "period": period, "time_ms": time_ms}
    orient = scene["orient"][team_id]
    own, other = scene["roles"][team_id], scene["roles"][rival]
    page = {"limit": 200}

    context = ("get_match_context", m)
    frame = ("get_tracking_frame", {**m, "period": period, "time_ms": time_ms})
    window = ("get_tracking_window", {**m, "scope": episode, "sample_step_ms": 1000})
    passes = ("get_passes", {**who, **in_scope, **page})
    events = ("get_events", {**m, **in_scope, **page})
    possessions = ("get_possessions", {**m, **in_scope, **page})
    defensive = ("get_defensive_actions", {**who, **in_scope, **page})
    # La serie es un agregado: debe pedirse ya filtrada por el mismo equipo.
    series = (
        "get_metric_series",
        {
            **(m if match_level else team),
            **in_scope,
            "profile_id": "finishing",
            "bin_s": 300,
            **page,
        },
    )
    network = ("get_passing_network", {**team, **in_scope, "view": "geometry"})

    if insight_id in PASS_TRACKING:
        pass_scope = scene["pass_windows"][team_id]
        pass_window = ("get_passes", {**team, "scope": pass_scope, **page})
        pass_tracking = (
            "get_tracking_window",
            {**m, "scope": pass_scope, "sample_step_ms": 1000},
        )
        oriented = {
            "team_id": team_id,
            "period": period,
            "attack_positive_x": orient,
            "tolerance_ms": PASS_TRACKING_TOLERANCE_MS,
        }
        if insight_id == "structural_pass":
            return [pass_window, pass_tracking], oriented
        # Las líneas que se rompen son las del rival.
        lines = {k: v for k, v in other.items() if k != "goalkeeper_id"}
        return [pass_window, pass_tracking, context], {**oriented, **lines}

    table = {
        "shot_map": ([("get_shots", {**who, **in_scope, **page})], p_scope),
        "xg_story": ([("get_shots", {**who, **in_scope, **page}), series], p_scope),
        "match_timeline": (
            [
                series,
                ("get_substitutions", {**m, **in_scope, **page}),
                ("get_discipline", {**m, **in_scope, **page}),
                events,
            ],
            {"period": intent.period},
        ),
        "pass_map": ([passes], p_scope),
        "passing_network": (
            [network, ("get_passes", {**team, **in_scope, **page})],
            {"team_id": team_id, "period": intent.period},
        ),
        "sequence_explorer": ([possessions], {"period": intent.period}),
        "defensive_actions": ([defensive], p_scope),
        "pressure_recovery": (
            [
                defensive,
                (
                    "get_sequences",
                    {**m, **in_scope, "pattern_id": "pressure_to_recovery", **page},
                ),
            ],
            p_scope,
        ),
        "ball_progression": (
            [("get_ball_actions", {**who, **in_scope, **page})],
            p_scope,
        ),
        "occupation_heatmap": (
            [("get_heatmap", {**team, **player, **in_scope, "grid_id": "5m", **page})],
            {"team_id": team_id, **player},
        ),
        "movement_profile": (
            [("get_movement_summary", {**team, **player, **in_scope})],
            {"team_id": team_id, **player},
        ),
        "play_replay": ([window, context], {"period": period}),
        "zone_presence": (
            [("get_zone_summary", {**team, **player, **in_scope})],
            {"team_id": team_id, **player},
        ),
        "team_shape": ([("get_team_shape", snapshot), frame], p_snap),
        "proximity_network": (
            [("get_proximity_connectivity", snapshot), frame],
            p_snap,
        ),
        "space_partition": (
            [("get_space_coverage", {**snapshot, "team_id": scene["focus"]}), frame],
            {"period": period, "time_ms": time_ms},
        ),
        "persistent_structure": ([("get_persistent_structure", snapshot)], p_snap),
        "node_robustness": (
            [
                (
                    "get_node_removal_robustness",
                    {**team, "period": period, "time_ms": time_ms},
                )
            ],
            p_snap,
        ),
        "entity_comparison": (
            [
                (
                    "compare_entities",
                    {
                        "match_ids": [intent.match_id],
                        "entity_kind": intent.compare_kind,
                        "entity_ids": intent.compare_ids
                        or [scene["home"], scene["away"]],
                        **in_scope,
                    },
                )
            ],
            {},
        ),
        "defensive_geometry": (
            [
                ("get_line_breaks", {**team, **in_scope, "view": "geometry"}),
                ("get_passes", {**team, **in_scope, **page}),
            ],
            {"team_id": team_id, "period": intent.period},
        ),
        "defensive_line_height": (
            [window, context],
            {**p_snap, **own, "attack_positive_x": orient},
        ),
        "goalkeeper_connection": (
            [window, context],
            {**p_snap, **own, "attack_positive_x": orient},
        ),
        "final_third_channels": (
            [
                ("get_passes", {**team, **in_scope, **page}),
                ("get_ball_actions", {**team, **in_scope, **page}),
            ],
            {"team_id": team_id, "period": intent.period},
        ),
        "ball_recovery_time": (
            [events, possessions],
            {"team_id": team_id, "period": intent.period},
        ),
        "pressure_turnovers": (
            [events, ("get_defensive_actions", {**m, **in_scope, **page})],
            {"team_id": team_id, "period": intent.period},
        ),
        "hodge_flow": ([network], {"team_id": team_id}),
        "topological_change": ([window], {"team_id": team_id}),
        "clearance_connectivity": ([window], p_snap),
    }
    return table[insight_id]
