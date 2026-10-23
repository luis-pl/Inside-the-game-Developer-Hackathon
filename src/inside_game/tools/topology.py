"""Reproducible spatial calculations; domain interpretations remain explicit."""

from math import hypot, isfinite

import gudhi
import networkx as nx
import numpy as np
from scipy.spatial import Delaunay, QhullError
from shapely.geometry import MultiPoint, Polygon

from inside_game.errors import DomainError


def cloud(players, team=None, outfield=True):
    selected = [
        p
        for p in players
        if (team is None or p["team_id"] == team)
        and p["position_status"] == "available"
        and p["is_on_pitch"]
        and (not outfield or not p.get("is_goalkeeper", p["on_pitch_slot"] == 1))
    ]
    if len(selected) < 2:
        raise DomainError(
            "INSUFFICIENT_COVERAGE",
            "At least two valid active player positions are required.",
        )
    return selected


def shape(players):
    xy = np.array([[p["x_m"], p["y_m"]] for p in players])
    center = xy.mean(axis=0)
    hull = MultiPoint(xy).convex_hull
    return {
        "players": len(players),
        "centroid_m": center.tolist(),
        "width_m": float(np.ptp(xy[:, 1])),
        "length_m": float(np.ptp(xy[:, 0])),
        "radius_of_gyration_m": float(
            np.sqrt(np.mean(np.sum((xy - center) ** 2, axis=1)))
        ),
        "hull_area_m2": hull.area,
        "hull_perimeter_m": hull.length,
        "hull_polygon_m": list(hull.exterior.coords)
        if hull.geom_type == "Polygon"
        else [],
        "degenerate": hull.geom_type != "Polygon",
    }


def proximity(players, epsilon=15, matrix=False):
    graph = nx.Graph()
    graph.add_nodes_from(p["player_id"] for p in players)
    complete = nx.Graph()
    complete.add_nodes_from(graph)
    distances = []
    for i, p in enumerate(players):
        row = []
        for j, q in enumerate(players):
            distance = hypot(p["x_m"] - q["x_m"], p["y_m"] - q["y_m"])
            row.append(distance)
            if j > i:
                complete.add_edge(p["player_id"], q["player_id"], weight=distance)
                if distance <= epsilon:
                    graph.add_edge(p["player_id"], q["player_id"], distance_m=distance)
        distances.append(row)
    components = sorted(
        (sorted(c) for c in nx.connected_components(graph)), key=lambda c: (-len(c), c)
    )
    mst = nx.minimum_spanning_tree(complete)
    result = {
        "epsilon_m": epsilon,
        "nodes": list(graph),
        "edges": [
            {"source": a, "target": b, **d} for a, b, d in graph.edges(data=True)
        ],
        "components": components,
        "component_count": len(components),
        "isolated_players": list(nx.isolates(graph)),
        "largest_component_fraction": len(components[0]) / len(players),
        "critical_connection_distance_m": max(
            (d["weight"] for _, _, d in mst.edges(data=True)), default=0
        ),
    }
    if matrix:
        result["distance_matrix_m"] = distances
        result["matrix_player_ids"] = [p["player_id"] for p in players]
    return result


def robustness(players, epsilon=15):
    before = proximity(players, epsilon)
    changes = []
    for p in players:
        remaining = [q for q in players if q["player_id"] != p["player_id"]]
        if len(remaining) < 2:
            components, fraction = 1, 1.0
        else:
            after = proximity(remaining, epsilon)
            components, fraction = (
                after["component_count"],
                after["largest_component_fraction"],
            )
        changes.append(
            {
                "removed_player_id": p["player_id"],
                "remaining_players": len(remaining),
                "component_count": components,
                "component_count_delta": components - before["component_count"],
                "largest_component_fraction": fraction,
            }
        )
    return {
        "baseline": before,
        "node_removals": changes,
        "interpretation": "Static mathematical perturbation, not a prediction of substitutions or red cards.",
    }


def persistence(players):
    points = [[p["x_m"], p["y_m"]] for p in players]
    tree = gudhi.RipsComplex(points=points, max_edge_length=40).create_simplex_tree(
        max_dimension=2
    )
    bars = tree.persistence(
        homology_coeff_field=2, min_persistence=0, persistence_dim_max=False
    )
    intervals = [
        {
            "dimension": dim,
            "birth_m": float(birth),
            "death_m": float(death) if isfinite(death) else None,
            "censored_at_40m": not isfinite(death),
        }
        for dim, (birth, death) in bars
        if dim <= 1
    ]
    betti = [
        {
            "epsilon_m": eps,
            "h0": sum(
                b["dimension"] == 0
                and b["birth_m"] <= eps
                and (b["death_m"] is None or eps < b["death_m"])
                for b in intervals
            ),
            "h1": sum(
                b["dimension"] == 1
                and b["birth_m"] <= eps
                and (b["death_m"] is None or eps < b["death_m"])
                for b in intervals
            ),
        }
        for eps in (5, 10, 15, 20)
    ]
    return {
        "method": "rips_h0_h1_f2_distance_le_epsilon",
        "maximum_edge_length_m": 40,
        "intervals": intervals,
        "betti": betti,
        "interpretation": "Abstract cycles across distance scales; not tactical gap polygons or time-persistent identities.",
    }


def _clip_halfplane(polygon, a, b, c):
    output = []
    if not polygon:
        return output
    for start, end in zip(polygon, polygon[1:] + polygon[:1]):
        vs, ve = a * start[0] + b * start[1] - c, a * end[0] + b * end[1] - c
        if vs <= 1e-9:
            output.append(start)
        if (vs < -1e-9 and ve > 1e-9) or (vs > 1e-9 and ve < -1e-9):
            u = vs / (vs - ve)
            output.append(
                (start[0] + u * (end[0] - start[0]), start[1] + u * (end[1] - start[1]))
            )
    return output


def coverage(players, length=105, width=68, triangulation=False):
    coords = [(p["x_m"], p["y_m"]) for p in players]
    if len(set(coords)) != len(coords):
        raise DomainError(
            "AMBIGUOUS_GEOMETRY",
            "Coincident positions make player territory assignment ambiguous.",
        )
    cells, totals = [], {}
    for i, p in enumerate(players):
        x, y = coords[i]
        polygon = [(0.0, 0.0), (length, 0.0), (length, width), (0.0, width)]
        for j, (qx, qy) in enumerate(coords):
            if i != j:
                polygon = _clip_halfplane(
                    polygon,
                    2 * (qx - x),
                    2 * (qy - y),
                    qx * qx + qy * qy - x * x - y * y,
                )
        area = Polygon(polygon).area if len(polygon) >= 3 else 0
        totals[p["team_id"]] = totals.get(p["team_id"], 0) + area
        cells.append(
            {
                "player_id": p["player_id"],
                "team_id": p["team_id"],
                "polygon_m": polygon,
                "area_m2": area,
            }
        )
    result = {
        "cells": cells,
        "team_area_m2": totals,
        "pitch_area_m2": length * width,
        "area_sum_m2": sum(totals.values()),
        "interpretation": "Nearest-player geometric allocation; not probability of controlling the ball.",
    }
    if triangulation:
        try:
            triangles = Delaunay(np.array(coords)).simplices
        except QhullError as exc:
            raise DomainError(
                "INSUFFICIENT_GEOMETRY", "Triangulation requires non-collinear sites."
            ) from exc
        result["triangles"] = [
            [players[int(i)]["player_id"] for i in triangle] for triangle in triangles
        ]
    return result


def corridor(start, end, opponents):
    dx, dy = end[0] - start[0], end[1] - start[1]
    norm = dx * dx + dy * dy
    if norm < 1e-12:
        raise DomainError(
            "INSUFFICIENT_GEOMETRY", "A corridor requires distinct endpoints."
        )
    rivals = []
    for p in opponents:
        t = ((p["x_m"] - start[0]) * dx + (p["y_m"] - start[1]) * dy) / norm
        if 0 < t < 1:
            distance = hypot(p["x_m"] - start[0] - t * dx, p["y_m"] - start[1] - t * dy)
            rivals.append(
                {
                    "player_id": p["player_id"],
                    "distance_to_segment_m": distance,
                    "projection": t,
                    "inside_corridor": distance <= 1.5,
                }
            )
    rivals.sort(key=lambda p: (p["distance_to_segment_m"], p["player_id"]))
    return {
        "start_m": start,
        "end_m": end,
        "half_width_m": 1.5,
        "opponents_between_endpoints": rivals,
        "opponents_in_corridor": sum(p["inside_corridor"] for p in rivals),
        "nearest_opponent_distance_m": rivals[0]["distance_to_segment_m"]
        if rivals
        else None,
        "interpretation": "Static 2D retrospective geometry; not interception probability.",
    }


def passing_network(data, rows, team, node_ids):
    graph = nx.DiGraph()
    graph.add_nodes_from(sorted(node_ids))
    for e in rows:
        p = e["pass"]
        if (
            e["team_id"] != team
            or not p
            or p["outcome"] is not None
            or p["recipient_player_id"] is None
        ):
            continue
        a, b = e["player_id"], p["recipient_player_id"]
        graph.add_edge(a, b, count=graph.get_edge_data(a, b, {}).get("count", 0) + 1)
    for _, _, d in graph.edges(data=True):
        d["cost"] = 1 / d["count"]
    centrality = nx.betweenness_centrality(graph, weight="cost", normalized=True)
    return {
        "nodes": [
            {
                "player_id": n,
                "in_strength": graph.in_degree(n, weight="count"),
                "out_strength": graph.out_degree(n, weight="count"),
                "betweenness": centrality[n],
            }
            for n in graph
        ],
        "edges": [
            {"source": a, "target": b, "passes": d["count"]}
            for a, b, d in graph.edges(data=True)
        ],
        "density": nx.density(graph),
        "directed": True,
        "components_weak": nx.number_weakly_connected_components(graph)
        if len(graph)
        else 0,
        "centrality_cost": "1 / completed_pass_count",
        "interpretation": "Aggregate network over the window; nodes need not be simultaneously active.",
    }
