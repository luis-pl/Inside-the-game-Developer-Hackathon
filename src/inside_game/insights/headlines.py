"""La respuesta en una frase: la cifra que contesta la pregunta de cada pieza.

Una pieza enseña datos; esta frase dice qué se ve en ellos, con los números ya
calculados (nunca texto de un modelo). Si una pieza no tiene qué decir devuelve
`None` y no se muestra nada: preferible a una frase vacía o inventada.
"""

from collections import Counter
from math import isfinite
from statistics import mean, median

from .identity import team as team_info
from .labels import EVENT_TYPES, metric_label


def plural(n, singular, many):
    return f"{n} {singular if n == 1 else many}"


def _num(value):
    return type(value) in (int, float) and isfinite(value)


def _team(block, key):
    return team_info(block, key)["name"]


def _player(block, key):
    info = block.players.get(str(key), {})
    if info.get("name"):
        return info["name"]
    if info.get("number") is not None:
        return f"shirt {info['number']}"
    return str(key)


def _metric(block, name):
    """Valor de una métrica sin el prefijo de consulta (`q3.xg` → `xg`)."""
    for key, value in block.metrics.items():
        if key.rsplit(".", 1)[-1] == name and _num(value):
            return value
    return None


def _fmt(key, value):
    if value is None:
        return "—"
    if key.endswith(("_rate", "_fraction")):
        return f"{value:.0%}"
    return f"{value:g}" if isinstance(value, float) else str(value)


def _by_team_text(block, limit=3):
    if not block.by_team:
        return None
    names = {t: _team(block, t) for t in block.by_team}
    keys = list(dict.fromkeys(k for row in block.by_team.values() for k in row))
    parts = []
    for key in keys[:limit]:
        label = metric_label(key, block.teams).removeprefix("Events · ")
        values = ", ".join(
            f"{names[t]} {_fmt(key, row.get(key))}" for t, row in block.by_team.items()
        )
        parts.append(f"{label}: {values}")
    return "; ".join(parts) or None


def shot_map(block):
    teams = Counter(p.get("team_id") for p in block.points)
    if not teams:
        return "No shots are recorded in this scope."
    goals = Counter(
        p.get("team_id") for p in block.points if p.get("outcome") == "Goal"
    )
    parts = []
    for team, count in sorted(teams.items(), key=lambda kv: -kv[1]):
        text = plural(count, "shot", "shots")
        if goals.get(team):
            text += f" ({plural(goals[team], 'goal', 'goals')})"
        parts.append(f"{_team(block, team)}: {text}" if len(teams) > 1 else text)
    return "; ".join(parts) + "."


def xg_story(block):
    total = _metric(block, "observed_xg")
    if total is None:
        return None
    return f"Cumulative xG for shots with available data is {total:.2f}."


def match_timeline(block):
    peaks = {}
    for item in block.series:
        key = item.get("team_id")
        if key is not None and item["value"] > peaks.get(key, (0,))[0]:
            peaks[key] = (item["value"], item["period"], item["time_ms"])
    parts = [
        f"{_team(block, key)} peaked in P{period} {ms // 60000}′ "
        f"({value:g} events in 5 min)"
        for key, (value, period, ms) in peaks.items()
    ]
    kinds = Counter(m["kind"] for m in block.markers)
    names = {
        "goal": ("goal", "goals"),
        "substitution": ("substitution", "substitutions"),
        "card": ("card", "cards"),
    }
    seen = [plural(kinds[k], *names[k]) for k in names if kinds.get(k)]
    if seen:
        parts.append("recorded " + ", ".join(seen))
    return ("; ".join(parts) + ".") if parts else None


def pass_map(block):
    done = _metric(block, "completed_passes")
    tried = _metric(block, "attempted_passes")
    rate = _metric(block, "completion_rate")
    if done is None:
        seen = len(block.vectors) or len(block.points)
        if not seen:
            return None
        return f"{plural(seen, 'recorded pass', 'recorded passes')}."
    if tried:
        extra = f" ({rate:.0%})" if _num(rate) else ""
        return f"{done:g} completed passes from {tried:g} attempted{extra}."
    return f"{done:g} completed passes (attempts are not recorded by the source)."


def passing_network(block):
    rows = [r for r in block.rows if _num(r.get("passes"))]
    if not rows:
        return None
    top = max(rows, key=lambda r: r["passes"])
    density = _metric(block, "density")
    extra = f" Connection density: {density:.2f}." if density is not None else ""
    return (
        f"The most frequent connection is {_player(block, top['source'])} → "
        f"{_player(block, top['target'])} ({top['passes']:g} passes).{extra}"
    )


def sequence_explorer(block):
    chains = [r for r in block.rows if isinstance(r.get("event_ids"), list)]
    if not chains:
        return None
    longest = max(len(r["event_ids"]) for r in chains)
    return (
        f"{plural(len(chains), 'chain', 'chains')} of actions; the longest has "
        f"{plural(longest, 'action', 'actions')}."
    )


def _counted(block, singular, many):
    text = _by_team_text(block)
    if text:
        return text + "."
    count = len(block.points) or len(block.rows)
    return f"{plural(count, singular, many)}." if count else None


def defensive_actions(block):
    return _counted(block, "recorded defensive action", "recorded defensive actions")


def pressure_recovery(block):
    count = len(block.rows)
    if not count:
        return None
    kinds = Counter(r.get("type_name") for r in block.rows if r.get("type_name"))
    top = ", ".join(
        f"{EVENT_TYPES.get(kind, kind)} {n}" for kind, n in kinds.most_common(3)
    )
    text = f"{plural(count, 'recorded action', 'recorded actions')}"
    if top:
        text += f" ({top})"
    if "Pressure" not in kinds:
        text += "; the source does not annotate pressures in this scope"
    return text + "."


def ball_progression(block):
    return _counted(block, "recorded ball action", "recorded ball actions")


def occupation_heatmap(block):
    rows = [r for r in block.rows if _num(r.get("seconds_in_zone"))]
    if not rows:
        return None
    top = max(rows, key=lambda r: r["seconds_in_zone"])
    return (
        f"Most occupied zone: around x {top['cell_x_m']:.0f} m, "
        f"y {top['cell_y_m']:.0f} m on the 105×68 m pitch "
        f"({top['seconds_in_zone']:.0f} player·s)."
    )


def movement_profile(block):
    rows = [r for r in block.rows if _num(r.get("distance_m"))]
    if not rows:
        return None
    top = max(rows, key=lambda r: r["distance_m"])
    who = (
        _player(block, top["player_id"])
        if top.get("player_id") is not None
        else "the group"
    )
    if len(rows) == 1 and top.get("player_id") is not None:
        return f"{who} covered {top['distance_m']:.0f} m."
    observed = plural(len(rows), "observed player", "observed players")
    return f"Greatest distance: {who} ({top['distance_m']:.0f} m) among {observed}."


def play_replay(block):
    times = [f["period_time_ms"] for f in block.frames if _num(f.get("period_time_ms"))]
    if len(times) < 2:
        return None
    return f"{len(times)} snapshots covering {(max(times) - min(times)) / 1000:.0f} s of play."


def zone_presence(block):
    seconds = _metric(block, "player_seconds_in_zone")
    if seconds is None:
        return None
    entries = _metric(block, "sampled_entries")
    extra = ""
    if entries:
        extra = f" across {plural(int(entries), 'sampled entry', 'sampled entries')}"
    return f"{seconds:.0f} player·s inside the zone{extra}."


def team_shape(block):
    width, length = _metric(block, "width_m"), _metric(block, "length_m")
    if width is None or length is None:
        return None
    area = _metric(block, "hull_area_m2")
    extra = f", with a {area:.0f} m² convex hull" if area is not None else ""
    return (
        f"At that instant the team shape was {width:.0f} m wide and "
        f"{length:.0f} m long{extra}."
    )


def proximity_network(block):
    count = _metric(block, "component_count")
    if count is None:
        return None
    text = plural(int(count), "connected group", "connected groups")
    eps = _metric(block, "epsilon_m")
    if eps is not None:
        text += f" at {eps:g} m"
    critical = _metric(block, "critical_connection_distance_m")
    if critical is not None:
        text += f"; all are connected from {critical:.1f} m"
    return text + "."


def space_partition(block):
    areas = {
        k.rsplit(".", 1)[-1]: v
        for k, v in block.metrics.items()
        if "team_area_m2." in k and _num(v)
    }
    total = _metric(block, "area_sum_m2") or sum(areas.values())
    if not areas or not total:
        return None
    parts = [
        f"{_team(block, t)} {a:.0f} m² ({a / total:.0%})"
        for t, a in sorted(areas.items(), key=lambda kv: -kv[1])
    ]
    return "Space nearest to each team: " + ", ".join(parts) + "."


def persistent_structure(block):
    dims = Counter(r.get("dimension") for r in block.rows)
    if not dims:
        return None
    return (
        f"{plural(dims.get(0, 0), 'persistent component', 'persistent components')} "
        f"and {plural(dims.get(1, 0), 'cycle', 'cycles')} across the connection scale."
    )


def node_robustness(block):
    rows = [r for r in block.rows if _num(r.get("component_count_delta"))]
    if not rows:
        return None
    top = max(rows, key=lambda r: r["component_count_delta"])
    delta = int(top["component_count_delta"])
    if delta <= 0:
        return "Removing any single player does not fragment the connection network."
    who = _player(block, top["removed_player_id"])
    more = plural(delta, "component", "components")
    return f"Removing {who} fragments the network the most (+{more})."


def entity_comparison(block):
    from .adapters import flatten_metrics

    rows = []
    for row in block.rows:
        if not isinstance(row, dict) or not isinstance(row.get("metrics", row), dict):
            continue
        values = {
            k: v
            for k, v in flatten_metrics(row.get("metrics", row)).items()
            if _num(v)
            and not k.endswith("_id")
            and not k.lower().startswith(("outcomes.", "body_parts."))
            and "unknown" not in k.lower()
        }
        rows.append((row.get("entity_id", row.get("player_id")), values))
    if len(rows) < 2:
        return None
    shared = [k for k in rows[0][1] if all(k in values for _, values in rows[1:])][:3]
    parts = []
    for key in shared:
        shown = [
            f"{_team(block, e) if str(e) in block.teams else _player(block, e)} "
            f"{_fmt(key.rsplit('.', 1)[-1], v[key])}"
            for e, v in rows
        ]
        joined = " versus ".join(shown) if len(shown) == 2 else " · ".join(shown)
        parts.append(f"{metric_label(key, block.teams)}: {joined}")
    return ("; ".join(parts) + ".") if parts else None


def defensive_geometry(block):
    observed = _metric(block, "observed_line_breaks")
    if observed is not None:
        mapped = _metric(block, "mapped_line_breaks")
        extra = f" ({mapped:g} mapped)" if mapped not in (None, observed) else ""
        verb = "pass crossed" if observed == 1 else "passes crossed"
        return f"{observed:g} {verb} opposition defensive lines{extra}."
    actions = _metric(block, "opponent_actions")
    if actions is None:
        return None
    return f"Analysed {actions:g} opposition actions against the defensive structure."


def defensive_line_height(block):
    height = _metric(block, "defensive_line_height_m")
    if height is None:
        return None
    return (
        "The defensive line (its deepest defender) was "
        f"{height:.1f} m from its goal line at that instant."
    )


def goalkeeper_connection(block):
    gap = _metric(block, "longitudinal_gap_m")
    if gap is None:
        return None
    keeper = _metric(block, "goalkeeper_height_m")
    line = _metric(block, "defensive_line_height_m")
    detail = ""
    if keeper is not None and line is not None:
        detail = f" (goalkeeper at {keeper:.1f} m, line at {line:.1f} m)"
    return f"Distance between goalkeeper and defensive line: {gap:.1f} m{detail}."


def final_third_channels(block):
    lanes = {
        int(k.rsplit("_", 1)[-1]): v
        for k, v in block.metrics.items()
        if k.rsplit(".", 1)[-1].startswith("channel_") and _num(v)
    }
    total = sum(lanes.values())
    if not total:
        return "No final-third entries are recorded in this scope."
    top = max(lanes, key=lanes.get)
    return (
        f"{plural(int(total), 'entry', 'entries')} into the final third; channel {top} "
        f"accounted for {lanes[top]:g} ({lanes[top] / total:.0%})."
    )


def between_lines_receptions(block):
    computed = _metric(block, "computed_passes")
    if computed is None:
        return None
    eligible = _metric(block, "eligible_passes")
    extra = ""
    if eligible is not None and eligible != computed:
        extra = f" (from {plural(int(eligible), 'eligible pass', 'eligible passes')})"
    kinds = Counter(r.get("category") for r in block.rows)
    if (
        kinds.get("between_lines")
        or kinds.get("behind_defense")
        or kinds.get("in_front")
    ):
        passes = plural(int(computed), "evaluated pass", "evaluated passes")
        return (
            f"Between-lines receptions: {kinds.get('between_lines', 0)} out of {passes}{extra} "
            f"({kinds.get('behind_defense', 0)} behind the defence, "
            f"{kinds.get('in_front', 0)} in front of the opposition midfield)."
        )
    return f"{plural(int(computed), 'evaluated pass', 'evaluated passes')}{extra}."


def ball_recovery_time(block):
    seconds = [r["recovery_s"] for r in block.rows if _num(r.get("recovery_s"))]
    if not seconds:
        return None
    return (
        f"Median of {median(seconds):.0f} s to recover the ball after losing it "
        f"(mean {mean(seconds):.0f} s, maximum {max(seconds):.0f} s; "
        f"{plural(len(seconds), 'recovery', 'recoveries')})."
    )


def pressure_turnovers(block):
    delays = [r["delay_s"] for r in block.rows if _num(r.get("delay_s"))]
    if not delays:
        return None
    return (
        f"{plural(len(delays), 'recovery', 'recoveries')} following pressure; "
        f"median delay of {median(delays):.1f} s."
    )


def structural_pass(block):
    rows = [r for r in block.rows if _num(r.get("relative_space_gain"))]
    if not rows:
        return None
    crossing = sum(1 for r in rows if (r.get("line_bypass_count") or 0) > 0)
    gain = median(r["relative_space_gain"] for r in rows)
    return (
        f"{plural(len(rows), 'evaluated pass', 'evaluated passes')}; bypass at least "
        f"one opposition line: {crossing}. Median space gain: {gain:.2f}."
    )


def hodge_flow(block):
    grad = _metric(block, "gradient_fraction")
    curl = _metric(block, "curl_fraction")
    harmonic = _metric(block, "harmonic_fraction")
    if None in (grad, curl, harmonic):
        return None
    return (
        f"Passing flow energy comprises {grad:.0%} gradient, "
        f"{curl:.0%} local circulation and {harmonic:.0%} harmonic."
    )


def topological_change(block):
    values = [s["value"] for s in block.series if _num(s.get("value"))]
    if not values:
        return None
    pairs = plural(len(values), "comparable pair", "comparable pairs")
    return f"Bottleneck distance ranged from {min(values):.1f} to {max(values):.1f} m across {pairs}."


def clearance_connectivity(block):
    rows = [r for r in block.rows if _num(r.get("full_width_m"))]
    if not rows:
        count = _metric(block, "reachable_players")
        if count is None:
            return None
        return f"{plural(int(count), 'player', 'players')} with a clear connection from the ball."
    widest = max(rows, key=lambda r: r["full_width_m"])
    if len(rows) == 1:
        who = _player(block, widest["player_id"])
        return f"1 player with a clear connection from the ball: {who} ({widest['full_width_m']:.1f} m)."
    return (
        f"{plural(len(rows), 'player', 'players')} with a clear connection from the ball; "
        f"the widest connects to {_player(block, widest['player_id'])} "
        f"({widest['full_width_m']:.1f} m)."
    )


HEADLINES = {
    "shot_map": shot_map,
    "xg_story": xg_story,
    "match_timeline": match_timeline,
    "pass_map": pass_map,
    "passing_network": passing_network,
    "sequence_explorer": sequence_explorer,
    "defensive_actions": defensive_actions,
    "pressure_recovery": pressure_recovery,
    "ball_progression": ball_progression,
    "occupation_heatmap": occupation_heatmap,
    "movement_profile": movement_profile,
    "play_replay": play_replay,
    "zone_presence": zone_presence,
    "team_shape": team_shape,
    "proximity_network": proximity_network,
    "space_partition": space_partition,
    "persistent_structure": persistent_structure,
    "node_robustness": node_robustness,
    "entity_comparison": entity_comparison,
    "defensive_geometry": defensive_geometry,
    "defensive_line_height": defensive_line_height,
    "goalkeeper_connection": goalkeeper_connection,
    "final_third_channels": final_third_channels,
    "between_lines_receptions": between_lines_receptions,
    "ball_recovery_time": ball_recovery_time,
    "pressure_turnovers": pressure_turnovers,
    "structural_pass": structural_pass,
    "hodge_flow": hodge_flow,
    "topological_change": topological_change,
    "clearance_connectivity": clearance_connectivity,
}


def headline(block):
    """Frase que responde la pregunta de la pieza, o None si no hay qué decir."""
    if block.state not in {"ready", "partial"}:
        return None
    try:
        text = HEADLINES[block.insight_id](block)
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        ZeroDivisionError,
        StopIteration,
    ):
        return None
    return text or None
