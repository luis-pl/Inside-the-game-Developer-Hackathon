"""De evidencia MCP a organismos; conserva alcance, faltantes y trazabilidad."""

from math import isfinite

from inside_game.errors import DomainError
from inside_game.insights import advanced
from inside_game.insights.catalog import RECIPES
from inside_game.insights.contracts import BlockData


def number(value):
    return type(value) in (int, float) and isfinite(value)


def flatten_metrics(value, prefix="", depth=0):
    result = {}
    if depth > 3:
        return result
    for key, item in value.items():
        name = f"{prefix}{key}"
        if number(item) or item is None:
            result[name] = item
        elif isinstance(item, dict):
            result.update(flatten_metrics(item, name + ".", depth + 1))
    return result


def clean_frames(evidence):
    frames = {}
    for e in evidence:
        for raw in e.response.data.get("frames", []):
            frame = {
                **raw,
                "players": [
                    p
                    for p in raw.get("players", [])
                    if p.get("position_status") == "available"
                    and p.get("is_on_pitch") is True
                    and number(p.get("x_m"))
                    and number(p.get("y_m"))
                ],
            }
            ball = raw.get("ball")
            frame["ball"] = (
                ball
                if ball
                and ball.get("position_status") == "available"
                and number(ball.get("x_m"))
                and number(ball.get("y_m"))
                else None
            )
            key = (frame["period"], frame["period_time_ms"])
            if key in frames and frames[key] != frame:
                raise ValueError("Snapshots incompatibles para el mismo instante.")
            frames[key] = frame
    return [frames[k] for k in sorted(frames)]


def event_items(evidence, operations=None):
    events = {}
    for e in evidence:
        if operations and e.operation not in operations:
            continue
        for item in e.response.data.get("items", []):
            if "event_id" in item and "period_time_ms" in item:
                events[item["event_id"]] = item
    return sorted(
        events.values(),
        key=lambda e: (e["period"], e["period_time_ms"], e.get("event_index", 0)),
    )


def map_events(block, events):
    block.coordinate_reference = "acting_team_attack"
    for e in events:
        x, y = e.get("location_x"), e.get("location_y")
        if not number(x) or not number(y):
            continue
        block.points.append(
            {
                "x": x * 105 / 120,
                "y": y * 68 / 80,
                "label": f"P{e['period']} {e['period_time_ms'] / 1000:g}s · {e.get('player_name') or e.get('player_id')}",
                "team_id": e.get("team_id"),
                "player_id": e.get("player_id"),
                "xg": (e.get("shot") or {}).get("statsbomb_xg"),
                "outcome": ((e.get("shot") or {}).get("outcome") or {}).get("name"),
            }
        )
        action = e.get("pass") or e.get("carry")
        if action and number(action.get("end_x")) and number(action.get("end_y")):
            block.vectors.append(
                {
                    "x": x * 105 / 120,
                    "y": y * 68 / 80,
                    "end_x": action["end_x"] * 105 / 120,
                    "end_y": action["end_y"] * 68 / 80,
                    "team_id": e.get("team_id"),
                    "player_id": e.get("player_id"),
                    "event_id": e["event_id"],
                    "failed": action.get("outcome") is not None,
                }
            )
    block.warnings.append(
        "Eventos: referencia de ataque del equipo actuante, normalizada a 105×68 m. No superpuesta a tracking fijo."
    )


def prepare(spec, all_evidence):
    recipe = RECIPES[spec.insight_id]
    selected = [e for e in all_evidence if e.evidence_id in spec.evidence_ids]
    b = BlockData(
        id=spec.id,
        insight_id=spec.insight_id,
        title=spec.title or recipe["title"],
        method_id=recipe["method_id"],
        evidence_ids=spec.evidence_ids,
        scope=[e.response.scope for e in selected],
        visual=spec.visual,
    )
    b.warnings = list(dict.fromkeys(w for e in selected for w in e.response.warnings))
    matches = {
        str(e.arguments.get("match_id"))
        for e in selected
        if e.arguments.get("match_id") is not None
    }
    if len(matches) > 1 and spec.insight_id != "entity_comparison":
        b.state = "incompatible"
        b.warnings.append(
            "Un bloque no puede mezclar partidos. Usa bloques independientes."
        )
        return b
    kinds = {e.response.provenance.get("is_synthetic") for e in selected}
    if len(kinds) > 1:
        b.state = "incompatible"
        b.warnings.append(
            "No se mezclan procedencias reales y sintéticas en el mismo bloque."
        )
        return b
    for e in selected:
        if e.operation in recipe["source_operations"]:
            if e.operation in {
                "get_metric_series",
                "get_heatmap",
                "get_movement_summary",
                "get_zone_summary",
                "get_passing_network",
            }:
                for field in ("team_id", "player_id"):
                    requested = getattr(spec.parameters, field)
                    if requested is not None and requested != e.arguments.get(field):
                        b.state = "incompatible"
                        b.warnings.append(
                            "Un agregado no puede filtrarse después de calcularse: solicita evidencia con el mismo participante."
                        )
                        return b
            for field in ("team_id", "player_id"):
                requested = getattr(spec.parameters, field)
                supplied = e.arguments.get(field)
                if (
                    requested is not None
                    and supplied is not None
                    and requested != supplied
                ):
                    b.state = "incompatible"
                    b.warnings.append(
                        "El filtro de participante de la evidencia no coincide con el bloque."
                    )
                    return b
    if not any(e.operation in recipe["source_operations"] for e in selected):
        b.state = "unavailable"
        b.warnings.append("Falta evidencia de las operaciones requeridas.")
        return b
    # Páginas finales solas no acreditan una consulta completa.
    for q in {e.query_id for e in selected}:
        pages = [e for e in selected if e.query_id == q]
        cursors = {e.arguments.get("cursor") for e in pages}
        if None not in cursors or any(
            e.response.pagination.get("next_cursor") not in cursors
            for e in pages
            if e.response.pagination.get("next_cursor")
        ):
            b.state = "partial"
            b.warnings.append(
                "Faltan páginas de una consulta; no se presenta como conjunto completo."
            )
    try:
        _populate(b, spec, selected)
    except ValueError as exc:
        b.state = "unavailable"
        b.warnings.append(str(exc))
    except (KeyError, TypeError, IndexError, OverflowError, DomainError):
        b.state = "error"
        b.warnings.append(
            "La estructura de la evidencia no permite calcular este bloque; revisa la operación y su contrato."
        )
    if b.state in {"error", "unavailable"}:
        for field in (
            "metrics",
            "points",
            "vectors",
            "series",
            "rows",
            "polygons",
            "frames",
        ):
            setattr(b, field, {} if field == "metrics" else [])
    if (
        not any(
            (b.metrics, b.points, b.vectors, b.series, b.rows, b.polygons, b.frames)
        )
        and b.state == "ready"
    ):
        b.state = "empty_with_coverage"
        b.warnings.append(
            "Resultado vacío; comprobar cobertura de la fuente antes de interpretarlo como cero."
        )
    b.warnings = list(dict.fromkeys(b.warnings))
    return b


def _populate(b, spec, evidence):
    key, p = spec.insight_id, spec.parameters
    relevant = [e for e in evidence if e.operation in RECIPES[key]["source_operations"]]
    events = event_items(relevant)
    if p.team_id is not None:
        events = [e for e in events if e.get("team_id") == p.team_id]
    if p.player_id is not None:
        events = [e for e in events if e.get("player_id") == p.player_id]
    if p.period is not None:
        events = [e for e in events if e.get("period") == p.period]
    if key in {"shot_map", "pass_map", "defensive_actions", "ball_progression"}:
        map_events(b, events)
        # Los resúmenes se repiten por página: sólo una vez por query_id.
        seen = set()
        for e in relevant:
            same_filter = all(
                getattr(p, field) is None or e.arguments.get(field) == getattr(p, field)
                for field in ("team_id", "player_id")
            )
            if e.query_id not in seen and same_filter:
                b.metrics.update(
                    {
                        f"{e.query_id}.{k}": v
                        for k, v in flatten_metrics(
                            e.response.data.get("summary", {})
                        ).items()
                    }
                )
                seen.add(e.query_id)
        b.metrics["events_in_supplied_evidence"] = len(events)
        b.rows = [
            {
                "period": e["period"],
                "time_ms": e["period_time_ms"],
                "player": e.get("player_name") or e.get("player_id"),
                "type": e.get("type_name"),
            }
            for e in events
        ]
    elif key == "xg_story":
        shots = [e for e in events if e.get("shot")]
        if not shots:
            totals = {}
            for e in relevant:
                if e.operation != "get_metric_series":
                    continue
                for item in e.response.data.get("series", []):
                    xg = item.get("metrics", {}).get("xg")
                    if not number(xg):
                        raise ValueError("xG no disponible en la serie de métricas.")
                    group = (e.arguments.get("team_id"), item["period"])
                    totals[group] = totals.get(group, 0) + xg
                    b.series.append(
                        {
                            "period": item["period"],
                            "time_ms": item["end_ms"],
                            "value": totals[group],
                            "group": str(group),
                            "team_id": group[0],
                        }
                    )
            if b.series:
                b.metrics = {"observed_xg": sum(totals.values())}
                b.unit = "xG"
                return
        if not shots or any(not number(e["shot"].get("statsbomb_xg")) for e in shots):
            raise ValueError(
                "xG no disponible para todos los tiros. No se sustituye por cero."
            )
        totals = {}
        for e in shots:
            group = (e["team_id"], e["period"])
            totals[group] = totals.get(group, 0) + e["shot"]["statsbomb_xg"]
            b.series.append(
                {
                    "period": e["period"],
                    "time_ms": e["period_time_ms"],
                    "value": totals[group],
                    "group": str(group),
                    "team_id": e["team_id"],
                }
            )
        b.metrics = {"observed_xg": sum(totals.values())}
        b.unit = "xG"
    elif key in {"occupation_heatmap", "zone_presence"}:
        scopes = {
            (
                str(e.arguments.get("scope", {})),
                e.arguments.get("team_id"),
                e.arguments.get("player_id"),
            )
            for e in relevant
            if e.operation == "get_heatmap"
        }
        if len(scopes) > 1:
            raise ValueError(
                "Usa bloques separados para mapas de calor de distintos equipos, jugadores o alcances; no se superponen agregados."
            )
        cells = {}
        seen_queries = set()
        for e in relevant:
            if e.query_id in seen_queries:
                continue
            seen_queries.add(e.query_id)
            data = e.response.data
            mode = data.get("mode", e.arguments.get("mode", "occupancy_seconds"))
            unit = "eventos" if mode == "event_count" else "s·jugador"
            if b.unit is not None and b.unit != unit:
                raise ValueError(
                    "No se mezclan conteos de eventos y segundos de ocupación en un mismo mapa."
                )
            b.unit = unit
            for c in data.get("cells", []):
                value = c.get("seconds_in_zone", c.get("seconds", c.get("events")))
                if value is None:
                    value = c.get("player_seconds")
                if value is not None:
                    cell = {
                        "cell": True,
                        "x": c.get("x_m", c.get("cell_x_m", 0)),
                        "y": c.get("y_m", c.get("cell_y_m", 0)),
                        "size": int(e.arguments.get("grid_id", "5m")[:-1]),
                        "value": value,
                        "team_id": e.arguments.get("team_id"),
                    }
                    cell_key = (cell["x"], cell["y"], cell["size"], cell["team_id"])
                    if cell_key in cells:
                        cells[cell_key]["value"] += value
                    else:
                        cells[cell_key] = cell
            b.metrics.update(
                flatten_metrics({k: v for k, v in data.items() if k != "cells"})
            )
            b.rows.extend(data.get("cells", []))
        b.polygons = list(cells.values())
    elif key in {
        "match_timeline",
        "sequence_explorer",
        "pressure_recovery",
        "movement_profile",
        "entity_comparison",
    }:
        for e in relevant:
            data = e.response.data
            rows = (
                data.get("players")
                or data.get("items")
                or data.get("entities")
                or data.get("comparisons")
                or []
            )
            b.rows.extend(rows if isinstance(rows, list) else [rows])
            for item in data.get("series", []):
                metrics = flatten_metrics(item.get("metrics", {}))
                chosen = next(((k, v) for k, v in metrics.items() if number(v)), None)
                if chosen:
                    b.series.append(
                        {
                            "period": item["period"],
                            "time_ms": item["start_ms"],
                            "value": chosen[1],
                            "group": chosen[0],
                        }
                    )
            if not rows and not data.get("series"):
                b.metrics.update(flatten_metrics(data))
            if key == "entity_comparison" and "reports" in data:
                b.rows.extend(data["reports"])
    elif key == "passing_network":
        for e in relevant:
            b.rows.extend(e.response.data.get("edges", []))
            b.metrics.update(
                flatten_metrics(
                    {
                        k: v
                        for k, v in e.response.data.items()
                        if k not in {"nodes", "edges"}
                    }
                )
            )
        b.points, b.vectors = network_geometry(b.rows)
        b.layout = "schematic"
        # Use observed pass origins and reception endpoints, never inferred
        # player positions. Require the same filters and scope as the aggregate.
        network = next(e for e in relevant if e.operation == "get_passing_network")
        bound_passes = [
            e
            for e in evidence
            if e.operation == "get_passes"
            and all(
                e.arguments.get(k, "all") == "all"
                for k in (
                    "height",
                    "restart",
                    "tagged",
                    "zone_id",
                    "score_state",
                    "pressure",
                )
            )
            and e.arguments.get("outcome", "all") in {"all", "complete"}
            and all(
                e.arguments.get(k) == network.arguments.get(k)
                for k in ("match_id", "team_id", "player_id", "scope")
            )
        ]
        samples = {}
        for event in event_items(bound_passes):
            action = event.get("pass") or {}
            if action.get("outcome") is not None:
                continue
            pairs = [
                (
                    event.get("player_id"),
                    event.get("location_x"),
                    event.get("location_y"),
                ),
                (
                    action.get("recipient_player_id"),
                    action.get("end_x"),
                    action.get("end_y"),
                ),
            ]
            for player, x, y in pairs:
                if player is not None and number(x) and number(y):
                    samples.setdefault(player, []).append((x * 105 / 120, y * 68 / 80))
        if b.points and all(n["id"] in samples for n in b.points):
            for node in b.points:
                coords = samples[node["id"]]
                node.update(
                    x=sum(x for x, _ in coords) / len(coords),
                    y=sum(y for _, y in coords) / len(coords),
                    observations=len(coords),
                )
            lookup = {node["id"]: node for node in b.points}
            for edge, visual in zip(b.rows, b.vectors, strict=True):
                visual.update(
                    x=lookup[edge["source"]]["x"],
                    y=lookup[edge["source"]]["y"],
                    end_x=lookup[edge["target"]]["x"],
                    end_y=lookup[edge["target"]]["y"],
                )
            b.layout = "pitch"
            b.coordinate_reference = "acting_team_attack"
            b.warnings.append(
                "Nodos: media de orígenes de pases y destinos de recepciones observados; no posición media de tracking."
            )
        else:
            b.warnings.append(
                "Red esquemática: faltan pases compatibles para situar todos los nodos en cancha."
            )
        for node in b.points:
            node["team_id"] = p.team_id or network.arguments.get("team_id")
            node["player_id"] = node["id"]
            node["involvement"] = sum(
                edge.get("passes", 0)
                for edge in b.rows
                if node["id"] in (edge["source"], edge["target"])
            )
        for edge in b.vectors:
            edge["team_id"] = p.team_id or network.arguments.get("team_id")
    elif key in {
        "team_shape",
        "proximity_network",
        "space_partition",
        "persistent_structure",
        "node_robustness",
        "defensive_geometry",
    }:
        for e in relevant:
            samples = e.response.data.get("samples", [])
            if key == "defensive_geometry" and e.operation == "get_line_breaks":
                eligible = [
                    s
                    for s in samples
                    if p.period is None or s.get("period") == p.period
                ]
                if p.time_ms is not None:
                    eligible = [s for s in eligible if s.get("time_ms") == p.time_ms]
                ids = {s["event_id"] for s in eligible}
                actions = [
                    a
                    for a in event_items(evidence, {"get_passes"})
                    if a["event_id"] in ids
                ]
                map_events(b, actions)
                b.rows.extend(eligible)
                b.metrics.update(
                    observed_line_breaks=len(eligible), mapped_line_breaks=len(actions)
                )
                if len(actions) < len(eligible):
                    b.state = "partial"
                    b.warnings.append(
                        "Faltan coordenadas de algunos pases: conserva las rupturas en tabla y aporta get_passes del mismo alcance para mapearlas."
                    )
                b.warnings.append(
                    "Ruptura geométrica de líneas según roles y tracking: no equivale a la etiqueta through_ball, que no está disponible en esta fuente."
                )
                continue
            if p.period is not None:
                samples = [s for s in samples if s.get("period") == p.period]
            if p.time_ms is not None:
                samples = [s for s in samples if s.get("time_ms") == p.time_ms]
            if not samples and e.response.data.get("samples"):
                raise ValueError(
                    "El snapshot solicitado no está en la evidencia espacial."
                )
            if len(samples) > 1:
                b.warnings.append(
                    "La geometría muestra el primer snapshot suministrado; el resto permanece en la evidencia."
                )
            for sample in samples[:1]:
                result = sample.get("result", sample)
                b.metrics.update(flatten_metrics(result))
                b.metrics["sample_time_ms"] = sample.get("time_ms")
                if key == "proximity_network":
                    b.points, b.vectors = network_geometry(
                        result.get("edges", []), result.get("nodes", [])
                    )
                    b.layout = "schematic"
                b.rows.extend(
                    result.get(
                        "intervals",
                        result.get("node_removals", result.get("edges", [])),
                    )
                )
                polygon = result.get("hull_polygon_m")
                if polygon:
                    b.polygons.append(
                        {"vertices": polygon, "value": 1, "team_id": p.team_id}
                    )
                for cell in result.get("cells", []):
                    b.polygons.append(
                        {
                            "vertices": cell.get("polygon_m", []),
                            "value": cell.get("area_m2", 0),
                            "team_id": cell.get("team_id"),
                            "player_id": cell.get("player_id"),
                        }
                    )
                b.rows.extend(result.get("betti", []))
            if not e.response.data.get("samples"):
                b.rows.append(e.response.data)
        frames = clean_frames(evidence)
        sample_time = b.metrics.get("sample_time_ms")
        frame = next(
            (
                f
                for f in frames
                if f["period_time_ms"] == sample_time
                and (p.period is None or f["period"] == p.period)
            ),
            None,
        )
        if frame and key in {
            "space_partition",
            "team_shape",
            "defensive_geometry",
            "proximity_network",
        }:
            selected = [
                x
                for x in frame["players"]
                if p.team_id is None or x["team_id"] == p.team_id
            ]
            b.points = [
                {
                    "x": x["x_m"],
                    "y": x["y_m"],
                    "player_id": x["player_id"],
                    "id": x["player_id"],
                    "team_id": x["team_id"],
                }
                for x in selected
            ]
            if key == "proximity_network":
                lookup = {x["id"]: x for x in b.points}
                b.vectors = [
                    {
                        "x": lookup[r["source"]]["x"],
                        "y": lookup[r["source"]]["y"],
                        "end_x": lookup[r["target"]]["x"],
                        "end_y": lookup[r["target"]]["y"],
                        "team_id": p.team_id,
                    }
                    for r in b.rows
                    if r.get("source") in lookup and r.get("target") in lookup
                ]
            b.layout = "pitch"
    elif key == "play_replay":
        b.frames = clean_frames(relevant)
        if not b.frames:
            raise ValueError(
                "No hay tracking. Capturas 360 no se convierten en tracking continuo."
            )
        if len({f["period"] for f in b.frames}) > 1:
            raise ValueError("Divide la reproducción en bloques por período.")
        b.metrics = {"observations": len(b.frames), "period": b.frames[0]["period"]}
        b.warnings.append(
            "Reproducción de muestras originales: sin interpolar huecos ni posiciones."
        )
    else:
        _advanced(b, spec, evidence, events)


def network_geometry(edges, node_ids=()):
    from math import cos, pi, sin

    nodes = sorted(
        {n for e in edges for n in (e["source"], e["target"])} | set(node_ids), key=str
    )
    points = [
        {
            "id": n,
            "x": 52.5 + 26 * cos(2 * pi * i / max(1, len(nodes))),
            "y": 34 + 26 * sin(2 * pi * i / max(1, len(nodes))),
            "label": str(n),
        }
        for i, n in enumerate(nodes)
    ]
    lookup = {p["id"]: p for p in points}
    vectors = [
        {
            "x": lookup[e["source"]]["x"],
            "y": lookup[e["source"]]["y"],
            "end_x": lookup[e["target"]]["x"],
            "end_y": lookup[e["target"]]["y"],
            "weight": e.get("passes", abs(e.get("net", 1))),
        }
        for e in edges
    ]
    return points, vectors


def _advanced(b, spec, evidence, events):
    key, p = spec.insight_id, spec.parameters
    frames = clean_frames(evidence)
    if p.period is not None:
        frames = [f for f in frames if f["period"] == p.period]
    frame = None
    if frames:
        frame = advanced.aligned_frame(
            frames,
            p.period or frames[0]["period"],
            p.time_ms if p.time_ms is not None else frames[0]["period_time_ms"],
            0,
        )
    if key in {
        "defensive_line_height",
        "goalkeeper_connection",
        "clearance_connectivity",
    }:
        if not frame:
            raise ValueError("Se necesita un frame de tracking válido.")
        if p.team_id is None:
            raise ValueError("Selecciona el equipo.")
        if key == "defensive_line_height":
            b.metrics = advanced.line_geometry(frame, p)
        elif key == "goalkeeper_connection":
            b.metrics = advanced.goalkeeper_connection(frame, p)
        else:
            result = advanced.clearance_graph(frame, p.team_id)
            b.rows = result["paths"]
            b.points = [{**x, "label": x["id"]} for x in result["nodes"]]
            lookup = {x["id"]: x for x in result["nodes"]}
            b.vectors = [
                {
                    "x": lookup[e["source"]]["x"],
                    "y": lookup[e["source"]]["y"],
                    "end_x": lookup[e["target"]]["x"],
                    "end_y": lookup[e["target"]]["y"],
                }
                for e in result["edges"]
            ]
            b.metrics = {"reachable_players": len(b.rows)}
        if not b.points:
            b.points = [
                {
                    "x": x["x_m"],
                    "y": x["y_m"],
                    "label": str(x["player_id"]),
                    "team_id": x["team_id"],
                }
                for x in frame["players"]
            ]
    elif key == "final_third_channels":
        b.rows = advanced.final_third_entries(events)
        b.points = b.rows
        b.metrics = {
            f"channel_{i + 1}": sum(r["channel"] == i for r in b.rows) for i in range(5)
        }
    elif key in {"between_lines_receptions", "structural_pass"}:
        b.rows = advanced.structural_pass(
            events, frames, p, receptions=key == "between_lines_receptions"
        )
        b.points = b.rows
        if not b.rows:
            raise ValueError(
                "Faltan pases, participantes/roles o snapshots sincronizados suficientes."
            )
        candidates = sum(
            bool(e.get("pass")) and e["pass"].get("outcome") is None for e in events
        )
        b.metrics.update(eligible_passes=candidates, computed_passes=len(b.rows))
        if len(b.rows) < candidates:
            b.state = "partial"
            b.warnings.append(
                "Se omitieron pases sin participantes, roles o snapshots compatibles; se informa el denominador."
            )
        if key == "structural_pass":
            b.vectors = b.rows
    elif key == "ball_recovery_time":
        if p.team_id is None:
            raise ValueError("Selecciona el equipo.")
        if not any(
            e.operation == "get_events"
            and e.arguments.get("team_id") is None
            and not e.arguments.get("event_types")
            for e in evidence
        ):
            raise ValueError(
                "Requiere get_events sin filtro por equipo ni tipo para observar transiciones."
            )
        b.rows = advanced.recovery_times(event_items(evidence), p.team_id)
        b.series = [
            {
                "period": r["period"],
                "time_ms": r["time_ms"],
                "value": r["recovery_s"],
                "group": "recovery_s",
            }
            for r in b.rows
        ]
    elif key == "pressure_turnovers":
        if p.team_id is None:
            raise ValueError("Selecciona el equipo.")
        if not any(
            e.operation == "get_events"
            and e.arguments.get("team_id") is None
            and not e.arguments.get("event_types")
            for e in evidence
        ):
            raise ValueError(
                "Requiere get_events sin filtro por equipo ni tipo para observar pérdidas y recuperaciones."
            )
        # No filtrar al rival: la secuencia necesita evidencia de ambos equipos.
        b.rows = advanced.pressure_turnovers(
            event_items(evidence), p.team_id, p.pressure_window_s
        )
        if not any(e.get("type_id") == 17 for e in event_items(evidence)):
            raise ValueError(
                "No hay presiones anotadas; no se infieren desde proximidad."
            )
        b.metrics = {"observed_sequences": len(b.rows)}
    elif key == "hodge_flow":
        edges = [
            edge
            for e in evidence
            if e.operation == "get_passing_network"
            for edge in e.response.data.get("edges", [])
        ]
        result = advanced.hodge(edges, p.mode)
        b.rows = result["edges"]
        b.metrics = {
            "net_flow_energy": result["energy"],
            **{f"{k}_fraction": v for k, v in (result["fractions"] or {}).items()},
            "reconstruction_error": result["reconstruction_error"],
            "orthogonality_error": result["orthogonality_error"],
        }
        b.points, b.vectors = network_geometry(b.rows)
        if result["fractions"] is None:
            b.warnings.append(
                "Flujo neto nulo: fracciones de energía indefinidas, no cero."
            )
        for point in b.points:
            point.update(team_id=p.team_id, player_id=point["id"])
        for edge in b.vectors:
            edge["team_id"] = p.team_id
    elif key == "topological_change":
        if p.team_id is None:
            raise ValueError("Selecciona el equipo.")
        if len(frames) > 300:
            raise ValueError(
                "Para persistencia temporal usa un máximo de 300 snapshots por bloque."
            )
        b.rows = advanced.temporal_topology(frames, p.team_id, p.max_gap_ms)
        b.metrics.update(supplied_frames=len(frames), comparable_pairs=len(b.rows))
        if len(b.rows) < max(0, len(frames) - 1):
            b.state = "partial"
            b.warnings.append(
                "Hay pares no comparables por huecos, cambios de identidad o censura; no se interpolaron."
            )
        b.series = [
            {
                "period": r["period"],
                "time_ms": r["time_ms"],
                "value": r["bottleneck_m"],
                "group": "bottleneck_m",
            }
            for r in b.rows
        ]
        if not b.rows:
            raise ValueError(
                "Sin pares consecutivos comparables con mismas identidades y H1 no censurado."
            )
    b.warnings.append(RECIPES[key]["availability_and_interpretation"])
