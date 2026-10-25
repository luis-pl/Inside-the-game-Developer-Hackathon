"""Extensiones locales inspiradas en FIFA/papers. No métricas FIFA certificadas.

Funciones puras: posiciones en metros, roles y dirección explícitos; ningún
modelo de lenguaje participa en los cálculos. Falta de requisitos => ValueError.
"""

from itertools import combinations, pairwise
from math import hypot

import gudhi
import networkx as nx
import numpy as np

from inside_game.tools import topology


def line_geometry(frame, p):
    if p.attack_positive_x is None or not p.defender_ids or p.team_id is None:
        raise ValueError("Se requieren orientación, equipo y defensores explícitos.")
    players = {x["player_id"]: x for x in frame["players"]}
    if not set(p.defender_ids) <= set(players):
        raise ValueError("Faltan posiciones de defensores declarados.")
    defenders = [players[i] for i in p.defender_ids]
    if any(x["team_id"] != p.team_id for x in defenders):
        raise ValueError("Los defensores no pertenecen al equipo seleccionado.")
    depth = lambda x: x["x_m"] if p.attack_positive_x else 105 - x["x_m"]
    height = min(depth(x) for x in defenders)
    own = [
        x
        for x in players.values()
        if x["team_id"] == p.team_id and x["player_id"] != p.goalkeeper_id
    ]
    if p.goalkeeper_id is None:
        raise ValueError(
            "Identifica el portero para excluirlo de la longitud del equipo."
        )
    if not own:
        raise ValueError("No hay jugadores de campo disponibles.")
    return {
        "defensive_line_height_m": height,
        "observed_outfield_length_m": max(map(depth, own)) - min(map(depth, own)),
    }


def goalkeeper_connection(frame, p):
    result = line_geometry(frame, p)
    players = {x["player_id"]: x for x in frame["players"]}
    keeper = players.get(p.goalkeeper_id)
    if not keeper or keeper["team_id"] != p.team_id:
        raise ValueError("Posición del portero no disponible para este equipo.")
    depth = keeper["x_m"] if p.attack_positive_x else 105 - keeper["x_m"]
    return {
        **result,
        "goalkeeper_height_m": depth,
        "longitudinal_gap_m": result["defensive_line_height_m"] - depth,
    }


def final_third_entries(events):
    rows = []
    for e in events:
        action = e.get("pass") or e.get("carry")
        if not action or (
            "pass" in e and e["pass"] and e["pass"].get("outcome") is not None
        ):
            continue
        if "carry" in e and e.get("carry") and e["carry"].get("outcome") is not None:
            continue
        x, y, end_x, end_y = (
            e.get("location_x"),
            e.get("location_y"),
            action.get("end_x"),
            action.get("end_y"),
        )
        if any(v is None for v in (x, y, end_x, end_y)):
            continue
        if x < 80 <= end_x:
            # Carril de llegada, no el punto interpolado de cruce. Convención local.
            rows.append(
                {
                    "event_id": e["event_id"],
                    "channel": min(4, max(0, int(end_y / 16))),
                    "x": end_x * 105 / 120,
                    "y": end_y * 68 / 80,
                }
            )
    return rows


def aligned_frame(frames, period, time_ms, tolerance_ms):
    eligible = [f for f in frames if f["period"] == period]
    if not eligible:
        raise ValueError("Sin snapshot del período solicitado.")
    f = min(
        eligible,
        key=lambda f: (abs(f["period_time_ms"] - time_ms), f["period_time_ms"]),
    )
    if abs(f["period_time_ms"] - time_ms) > tolerance_ms:
        raise ValueError(
            "No hay snapshot sincronizado dentro de la tolerancia declarada."
        )
    return f


def fixed_endpoint(e, p, end=False):
    if p.attack_positive_x is None:
        raise ValueError(
            "Se requiere orientación del equipo para alinear eventos y tracking."
        )
    raw = e.get("pass") if end else e
    x = raw.get("end_x" if end else "location_x")
    y = raw.get("end_y" if end else "location_y")
    if x is None or y is None:
        raise ValueError("Coordenadas de pase ausentes.")
    x, y = x * 105 / 120, y * 68 / 80
    return (x, y) if p.attack_positive_x else (105 - x, 68 - y)


def structural_pass(events, frames, p, receptions=False):
    rows = []
    if p.team_id is None:
        raise ValueError("Selecciona el equipo pasador.")
    for e in events:
        if (
            not e.get("pass")
            or e["team_id"] != p.team_id
            or e["pass"].get("outcome") is not None
        ):
            continue
        start = fixed_endpoint(e, p)
        end = fixed_endpoint(e, p, True)
        # Inicio: descriptores LBS/SGM. Final: recepción, usando duración anotada.
        duration = e.get("duration")
        if receptions and duration is None:
            continue
        time_ms = e["period_time_ms"] + (round(duration * 1000) if receptions else 0)
        try:
            frame = aligned_frame(frames, e["period"], time_ms, p.tolerance_ms)
        except ValueError:
            continue
        opponents = [x for x in frame["players"] if x["team_id"] != p.team_id]
        if len(opponents) < 2:
            continue
        orient = 1 if p.attack_positive_x else -1
        if receptions:
            players = {x["player_id"]: x for x in opponents}
            if (
                not p.defender_ids
                or not p.midfielder_ids
                or not set(p.defender_ids + p.midfielder_ids) <= set(players)
            ):
                continue
            defensive = max(orient * players[i]["x_m"] for i in p.defender_ids)
            midfield = max(orient * players[i]["x_m"] for i in p.midfielder_ids)
            if defensive <= midfield:
                continue
            category = (
                "behind_defense"
                if orient * end[0] > defensive
                else "between_lines"
                if midfield < orient * end[0] <= defensive
                else "in_front"
            )
            rows.append(
                {
                    "event_id": e["event_id"],
                    "x": end[0],
                    "y": end[1],
                    "category": category,
                    "snapshot_time_ms": frame["period_time_ms"],
                }
            )
        else:
            participants = {x["player_id"]: x for x in frame["players"]}
            passer = participants.get(e.get("player_id"))
            receiver = participants.get(e["pass"].get("recipient_player_id"))
            if (
                not passer
                or not receiver
                or passer["team_id"] != p.team_id
                or receiver["team_id"] != p.team_id
            ):
                continue
            start = (passer["x_m"], passer["y_m"])
            end = (receiver["x_m"], receiver["y_m"])
            before = sum(orient * x["x_m"] > orient * start[0] for x in opponents)
            after = sum(orient * x["x_m"] > orient * end[0] for x in opponents)
            nearest = lambda point, opponents=opponents: min(
                hypot(x["x_m"] - point[0], x["y_m"] - point[1]) for x in opponents
            )
            rows.append(
                {
                    "event_id": e["event_id"],
                    "line_bypass_count": before - after,
                    "relative_space_gain": nearest(end) / max(1.5, nearest(start)),
                    "x": start[0],
                    "y": start[1],
                    "end_x": end[0],
                    "end_y": end[1],
                    "snapshot_time_ms": frame["period_time_ms"],
                }
            )
    return rows


def recovery_times(events, team_id):
    # Sólo eventos de control anotados. Defensa/presión no se consideran posesión.
    controls = [
        e
        for e in events
        if e.get("type_id") in {30, 42, 43} and e.get("team_id") is not None
    ]
    rows = []
    for period in sorted({e["period"] for e in controls}):
        ordered = sorted(
            (e for e in controls if e["period"] == period),
            key=lambda e: (e["period_time_ms"], e.get("event_index", 0)),
        )
        last_own, lost = None, None
        for e in ordered:
            if e["team_id"] == team_id:
                if lost is not None:
                    rows.append(
                        {
                            "period": period,
                            "time_ms": e["period_time_ms"],
                            "recovery_s": (e["period_time_ms"] - lost) / 1000,
                            "event_id": e["event_id"],
                        }
                    )
                    lost = None
                last_own = e["period_time_ms"]
            elif last_own is not None and lost is None:
                lost = last_own
    return rows


def pressure_turnovers(events, team_id, window_s):
    rows, credited = [], set()
    ordered = sorted(
        events,
        key=lambda e: (e["period"], e["period_time_ms"], e.get("event_index", 0)),
    )
    for index, pressure in enumerate(ordered):
        if pressure.get("type_id") != 17 or pressure.get("team_id") != team_id:
            continue
        following = [
            e
            for e in ordered[index + 1 :]
            if e["period"] == pressure["period"]
            and 0 <= e["period_time_ms"] - pressure["period_time_ms"] <= window_s * 1000
            and e.get("type_id") in {2, 3, 10, 14, 30, 42, 43}
        ]
        loss_seen = False
        for e in following:
            if e.get("team_id") != team_id and (
                e.get("type_id") == 3
                or (e.get("pass") or {}).get("outcome") is not None
            ):
                loss_seen = True
            if (
                loss_seen
                and e.get("team_id") == team_id
                and e.get("type_id") in {2, 10, 42}
            ):
                if e["event_id"] not in credited:
                    credited.add(e["event_id"])
                    rows.append(
                        {
                            "pressure_event_id": pressure["event_id"],
                            "recovery_event_id": e["event_id"],
                            "delay_s": (
                                e["period_time_ms"] - pressure["period_time_ms"]
                            )
                            / 1000,
                        }
                    )
                break
    return rows


def hodge(edges, mode="clique"):
    weights = {}
    for edge in edges:
        a, b = edge["source"], edge["target"]
        if a == b:
            continue
        pair = tuple(sorted((a, b)))
        weights[pair] = weights.get(pair, 0) + (1 if a < b else -1) * edge.get(
            "passes", 1
        )
    pairs, nodes = sorted(weights), sorted({n for pair in weights for n in pair})
    if not pairs:
        raise ValueError("Sin aristas de pases observados.")
    if len(nodes) > 40:
        raise ValueError("El análisis Hodge se limita a 40 participantes.")
    incidence = np.array(
        [[int(n == b) - int(n == a) for a, b in pairs] for n in nodes], float
    )
    boundaries = []
    if mode == "clique":
        for a, b, c in combinations(nodes, 3):
            if all(pair in weights for pair in ((a, b), (a, c), (b, c))):
                boundaries.append(
                    [
                        1 if edge in ((a, b), (b, c)) else -1 if edge == (a, c) else 0
                        for edge in pairs
                    ]
                )
    flow = np.array([weights[pair] for pair in pairs], float)
    project = lambda matrix: (
        matrix @ np.linalg.lstsq(matrix, flow, rcond=None)[0]
        if matrix.shape[1]
        else np.zeros_like(flow)
    )
    gradient = project(incidence.T)
    curl = project(np.array(boundaries, float).T) if boundaries else np.zeros_like(flow)
    harmonic = flow - gradient - curl
    energy = float(flow @ flow)
    energies = {
        "gradient": float(gradient @ gradient),
        "curl": float(curl @ curl),
        "harmonic": float(harmonic @ harmonic),
    }
    return {
        "energy": energy,
        "fractions": {k: v / energy for k, v in energies.items()}
        if energy > 1e-12
        else None,
        "energies": energies,
        "edges": [
            {
                "source": a,
                "target": b,
                "net": float(flow[i]),
                "gradient": float(gradient[i]),
                "curl": float(curl[i]),
                "harmonic": float(harmonic[i]),
            }
            for i, (a, b) in enumerate(pairs)
        ],
        "reconstruction_error": float(
            np.linalg.norm(flow - gradient - curl - harmonic)
        ),
        "orthogonality_error": float(
            max(abs(gradient @ curl), abs(gradient @ harmonic), abs(curl @ harmonic))
        )
        / max(1, energy),
        "mode": mode,
    }


def temporal_topology(frames, team_id, max_gap_ms):
    rows, previous = [], None
    for frame in frames:
        players = [x for x in frame["players"] if x["team_id"] == team_id]
        ids = tuple(sorted(x["player_id"] for x in players))
        if len(players) < 3:
            previous = None
            continue
        diagram = topology.persistence(players)["intervals"]
        # H1 censurado no tiene muerte conocida: no sustituir infinito por 40.
        if any(b["dimension"] == 1 and b["death_m"] is None for b in diagram):
            previous = None
            continue
        points = np.array(
            [[b["birth_m"], b["death_m"]] for b in diagram if b["dimension"] == 1],
            float,
        ).reshape((-1, 2))
        if (
            previous
            and previous[0] == frame["period"]
            and previous[1] == ids
            and 0 < frame["period_time_ms"] - previous[2] <= max_gap_ms
        ):
            rows.append(
                {
                    "period": frame["period"],
                    "time_ms": frame["period_time_ms"],
                    "bottleneck_m": float(
                        gudhi.bottleneck_distance(previous[3], points)
                    ),
                }
            )
        previous = (frame["period"], ids, frame["period_time_ms"], points)
    return rows


def clearance_graph(frame, team_id):
    if frame.get("ball") is None:
        raise ValueError("Balón ausente.")
    ball = frame["ball"]
    nodes = [{"id": "ball", "x": ball["x_m"], "y": ball["y_m"]}] + [
        {"id": str(p["player_id"]), "x": p["x_m"], "y": p["y_m"]}
        for p in frame["players"]
        if p["team_id"] == team_id
    ]
    opponents = [
        (p["x_m"], p["y_m"]) for p in frame["players"] if p["team_id"] != team_id
    ]
    if not opponents or len(nodes) < 2:
        raise ValueError("Faltan posiciones de ambos equipos.")
    sites = [(p["x_m"], p["y_m"]) for p in frame["players"]] + [
        (ball["x_m"], ball["y_m"])
    ]
    graph = nx.Graph()
    graph.add_nodes_from(n["id"] for n in nodes)
    for a, b in combinations(nodes, 2):
        ax, ay, bx, by = a["x"], a["y"], b["x"], b["y"]
        norm = (bx - ax) ** 2 + (by - ay) ** 2
        if norm < 1e-18:
            # Balón coincidente con un jugador: identidad distinta, enlace neutro.
            graph.add_edge(a["id"], b["id"], clearance=0.0, coincident=True)
            continue
        if any(
            (x - ax) * (x - bx) + (y - ay) * (y - by) < -1e-9
            for x, y in sites
            if hypot(x - ax, y - ay) > 1e-9 and hypot(x - bx, y - by) > 1e-9
        ):
            continue

        def distance(point, ax=ax, ay=ay, bx=bx, by=by, norm=norm):
            x, y = point
            t = max(0, min(1, ((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / norm))
            return hypot(x - ax - t * (bx - ax), y - ay - t * (by - ay))

        radius = max(
            0,
            min(
                ax,
                bx,
                105 - ax,
                105 - bx,
                ay,
                by,
                68 - ay,
                68 - by,
                *map(distance, opponents),
            ),
        )
        if radius > 1e-9:
            graph.add_edge(a["id"], b["id"], clearance=radius)
    # Co-localización del balón se contrae antes de calcular el cuello de botella.
    coincident = next(
        (
            n["id"]
            for n in nodes[1:]
            if hypot(n["x"] - ball["x_m"], n["y"] - ball["y_m"]) < 1e-9
        ),
        None,
    )
    if coincident:
        for target, attrs in list(graph[coincident].items()):
            if target != "ball":
                graph.add_edge("ball", target, **attrs)
        graph.remove_edge("ball", coincident)
    forest = nx.maximum_spanning_tree(graph, weight="clearance")
    rows = []
    for node in nodes[1:]:
        if node["id"] == coincident:
            continue
        if nx.has_path(forest, "ball", node["id"]):
            path = nx.shortest_path(forest, "ball", node["id"])
            radius = min(forest[a][b]["clearance"] for a, b in pairwise(path))
            rows.append(
                {
                    "player_id": node["id"],
                    "bottleneck_radius_m": radius,
                    "full_width_m": 2 * radius,
                    "path": path,
                }
            )
    return {
        "nodes": nodes,
        "edges": [
            {"source": a, "target": b, **d} for a, b, d in graph.edges(data=True)
        ],
        "paths": rows,
    }
