"""Hechos de fuentes y métricas del renderer; el LLM no puede crear sus valores."""

import hashlib
import json
import re
from math import isfinite

from inside_game.agents.analyst_contracts import Fact
from inside_game.agents.experiments import experiment
from inside_game.insights.source_policy import annotated_summary

TOKEN = re.compile(r"\{\{(f-[0-9a-f]{12})\}\}")


def source_key(evidence):
    return json.dumps(
        [
            evidence.operation,
            evidence.arguments,
            evidence.response.model_dump(mode="json"),
        ],
        sort_keys=True,
    )


def fact(value, label, evidence, path, *, block_id=None, scope=None, operation=None):
    if "/team_area_m2/" in path:
        label = "team_area_m2." + path.rsplit("/", 1)[-1]
    population = (
        "outfield_players"
        if evidence.operation
        in {
            "get_team_shape",
            "get_proximity_connectivity",
            "get_persistent_structure",
            "get_node_removal_robustness",
        }
        else "all_active_players"
        if evidence.operation == "get_space_coverage"
        else None
    )
    identifier = hashlib.sha256(
        json.dumps(
            [evidence.evidence_id, path, value, block_id], sort_keys=True
        ).encode()
    ).hexdigest()[:12]
    return Fact(
        id="f-" + identifier,
        value=value,
        label=label,
        evidence_ids=[evidence.evidence_id],
        operation=operation or evidence.operation,
        path=path,
        scope={
            **(
                scope
                or {
                    **evidence.response.scope,
                    **{
                        k: evidence.arguments[k]
                        for k in (
                            "match_id",
                            "team_id",
                            "period",
                            "time_ms",
                            "epsilon_m",
                        )
                        if evidence.arguments.get(k) is not None
                    },
                }
            ),
            **({"population": population} if population else {}),
        },
        provenance=evidence.response.provenance,
        block_id=block_id,
        unit="m²"
        if label.endswith("_m2") or label.startswith("team_area_m2.")
        else "ms"
        if label.endswith("_ms")
        else "m"
        if label.endswith("_m")
        else "proporción"
        if label.endswith(("_rate", "_fraction"))
        else None,
    )


SAMPLE_SUMMARY_THRESHOLD = 5


def numeric_leaves(value, prefix=""):
    """Métricas numéricas de un resultado anidado, con nombre aplanado."""
    if type(value) in (int, float) and isfinite(value):
        return {prefix: value}
    if isinstance(value, dict):
        leaves = {}
        for key, item in value.items():
            if key in {"interpretation", "method", "note", "description", "warnings"}:
                continue
            leaves.update(
                numeric_leaves(item, f"{prefix}_{key}" if prefix else str(key))
            )
        return leaves
    return {}


def summarize_samples(samples):
    """Resumen de una ventana: número de muestras, extremos y estadísticos."""
    series = {}
    for sample in samples:
        for name, number in numeric_leaves(sample.get("result", {})).items():
            series.setdefault(name, []).append(number)
    summary = {
        "samples": len(samples),
        "period": samples[0].get("period"),
        "time_ms_start": samples[0].get("time_ms"),
        "time_ms_end": samples[-1].get("time_ms"),
    }
    for name, values in series.items():
        summary[f"{name}_mean"] = round(sum(values) / len(values), 3)
        summary[f"{name}_min"] = min(values)
        summary[f"{name}_max"] = max(values)
        summary[f"{name}_first"] = values[0]
        summary[f"{name}_last"] = values[-1]
    return {k: v for k, v in summary.items() if v is not None}


def scalar_facts(value, evidence, path, *, block_id=None, scope=None, depth=0):
    if depth > 6:
        return []
    if (
        type(value) in (int, float)
        and isfinite(value)
        or isinstance(value, str)
        and 0 < len(value) <= 120
    ):
        return [
            fact(
                value,
                path.rsplit("/", 1)[-1],
                evidence,
                path,
                block_id=block_id,
                scope=scope,
            )
        ]
    if isinstance(value, dict):
        return [
            f
            for key, item in value.items()
            if key
            not in {"interpretation", "method", "note", "description", "warnings"}
            for f in scalar_facts(
                item,
                evidence,
                path + "/" + str(key),
                block_id=block_id,
                scope=scope,
                depth=depth + 1,
            )
        ]
    if isinstance(value, list) and path.rsplit("/", 1)[-1] in {
        "betti",
        "intervals",
        "node_removals",
    }:
        return [
            f
            for i, row in enumerate(value)
            if isinstance(row, dict)
            for f in scalar_facts(
                row,
                evidence,
                path + "/" + str(i),
                block_id=block_id,
                scope={
                    **(scope or {}),
                    **{
                        key: row[key]
                        for key in (
                            "epsilon_m",
                            "removed_player_id",
                            "dimension",
                            "censored_at_40m",
                        )
                        if key in row
                    },
                },
                depth=depth + 1,
            )
        ]
    return []  # Coordenadas, filas y ausencias no se sustituyen por cifras inventadas.


def evidence_facts(evidence):
    facts = []
    names = {
        (ev.arguments.get("match_id"), row["player_id"]): row["player_name"]
        for ev in evidence
        if ev.operation == "get_match_context"
        for row in ev.response.data.get("lineups", [])
        if row.get("player_id") is not None and row.get("player_name")
    }
    episode = any(
        ev.operation in {"get_tracking_window", "get_event_context"} for ev in evidence
    )
    participants = (
        {
            player
            for ev in evidence
            if ev.operation == "get_passes"
            and 0 < len(ev.response.data.get("items", [])) <= 8
            for row in ev.response.data["items"]
            for player in (
                row.get("player_id"),
                (row.get("pass") or {}).get("recipient_player_id"),
            )
            if player is not None
        }
        if episode
        else set()
    )
    ranked_players = {
        row.get("entity_id")
        for ev in evidence
        if ev.operation == "get_rankings"
        and ev.arguments.get("entity_kind", "player") == "player"
        for row in ev.response.data.get("items", [])
        if type(row.get("rank")) is int and 1 <= row["rank"] <= 5
    }
    for ev in evidence:
        data = ev.response.data
        if ev.operation == "get_match_context":
            for i, row in enumerate(data.get("lineups", [])):
                if row.get("player_id") in participants and row.get("player_name"):
                    facts.append(
                        fact(
                            row["player_name"],
                            "player_name",
                            ev,
                            f"/data/lineups/{i}/player_name",
                            scope={
                                **ev.response.scope,
                                "match_id": ev.arguments.get("match_id"),
                                "player_id": row["player_id"],
                            },
                        )
                    )
        # Short episodes can be narrated from recorded pass links, rather than
        # only aggregate counts. Never silently sample a longer event sequence.
        items = data.get("items", [])
        if (
            episode
            and ev.operation == "get_passes"
            and 0 < len(items) <= 8
            and data.get("total") == len(items)
        ):
            for i, event in enumerate(items):
                target = (event.get("pass") or {}).get("recipient_player_id")
                source_name = names.get(
                    (ev.arguments.get("match_id"), event.get("player_id"))
                )
                target_name = names.get((ev.arguments.get("match_id"), target))
                if not source_name or not target_name or not event.get("timestamp"):
                    continue
                facts.append(
                    fact(
                        f"{event['timestamp']} · {source_name} → {target_name}",
                        "recorded_pass_link",
                        ev,
                        f"/data/items/{i}#pass_link",
                        scope={
                            **ev.response.scope,
                            "match_id": ev.arguments.get("match_id"),
                            "period": event.get("period"),
                            "event_id": event.get("event_id"),
                            "event_order": i,
                            "endpoint_observations_only": True,
                        },
                    )
                )
        for key in ("summary", "metrics", "match"):
            values = data.get(key, {})
            if key in {"summary", "metrics"} and isinstance(values, dict):
                values = annotated_summary(ev, values)
            facts.extend(scalar_facts(values, ev, "/data/" + key))
        ranking_rows = [
            (i, row)
            for i, row in enumerate(data.get("items", []))
            if type(row.get("rank")) is int and 1 <= row["rank"] <= 5
        ]
        if ev.operation == "get_rankings" and ranking_rows:
            facts.extend(
                scalar_facts(
                    {k: data[k] for k in ("metric", "normalization") if k in data},
                    ev,
                    "/data",
                )
            )
            for i, row in ranking_rows:
                facts.extend(
                    scalar_facts(
                        row,
                        ev,
                        f"/data/items/{i}",
                        scope={
                            **ev.response.scope,
                            "metric": data.get("metric"),
                            "normalization": data.get("normalization"),
                            "entity_id": row.get("entity_id"),
                            "match_id": ev.arguments.get("match_ids", [None])[0]
                            if len(ev.arguments.get("match_ids", [])) == 1
                            else None,
                            "player_id"
                            if ev.arguments.get("entity_kind", "player") == "player"
                            else "team_id": row.get("entity_id"),
                            "rank": row.get("rank"),
                            "ranked_rows_supplied": len(data.get("items", [])),
                            "rank_limit_in_analysis": 5,
                        },
                    )
                )
        if ev.operation == "get_match_context" and ranked_players:
            for i, row in enumerate(data.get("lineups", [])):
                if row.get("player_id") in ranked_players:
                    facts.extend(
                        scalar_facts(
                            {
                                k: row[k]
                                for k in ("player_id", "player_name", "team_id")
                                if k in row
                            },
                            ev,
                            f"/data/lineups/{i}",
                            scope={**ev.response.scope, "player_id": row["player_id"]},
                        )
                    )
        if ev.operation in {"list_matches", "find_entities"}:
            for i, item in enumerate(data.get("items", [])):
                keys = {
                    "match_id",
                    "home_team_id",
                    "home_team_name",
                    "away_team_id",
                    "away_team_name",
                    "match_date",
                    "team_id",
                    "team_name",
                    "player_id",
                    "player_name",
                }
                facts.extend(
                    scalar_facts(
                        {k: v for k, v in item.items() if k in keys},
                        ev,
                        f"/data/items/{i}",
                        scope={
                            **ev.response.scope,
                            **{
                                k: item[k]
                                for k in ("match_id", "team_id", "player_id")
                                if item.get(k) is not None
                            },
                        },
                    )
                )
                if len(facts) > 220:
                    raise ValueError("FACT_BUDGET_EXCEEDED")
        samples = data.get("samples", [])
        if experiment("samples") and len(samples) > SAMPLE_SUMMARY_THRESHOLD:
            # EXPERIMENTO LOCAL: una ventana a 1 Hz generaba un hecho por métrica
            # y segundo (más de 220). Se resume cada métrica de la ventana.
            facts.extend(
                scalar_facts(
                    summarize_samples(samples),
                    ev,
                    "/data/samples_summary",
                    scope={**ev.response.scope, **ev.arguments},
                )
            )
            samples = []
        for i, sample in enumerate(samples):
            facts.extend(
                scalar_facts(
                    {k: sample[k] for k in ("period", "time_ms") if k in sample},
                    ev,
                    f"/data/samples/{i}",
                    scope={**ev.response.scope, **ev.arguments},
                )
            )
            if len(facts) > 220:
                raise ValueError("FACT_BUDGET_EXCEEDED")
            facts.extend(
                scalar_facts(
                    sample.get("result", {}),
                    ev,
                    f"/data/samples/{i}/result",
                    scope={
                        **ev.response.scope,
                        **ev.arguments,
                        "period": sample.get("period"),
                        "time_ms": sample.get("time_ms"),
                    },
                )
            )
        if ev.operation in {"get_tracking_frame", "get_tracking_window"}:
            step = ev.response.coverage.get("returned_step_ms")
            if type(step) is int and step > 0:
                facts.append(
                    fact(
                        1000 / step,
                        "sampling_hz",
                        ev,
                        "/coverage/returned_step_ms#frequency_hz",
                    ).model_copy(update={"unit": "Hz"})
                )
            facts.append(
                fact(
                    len(data.get("frames", [])),
                    "frames suministrados",
                    ev,
                    "/data/frames#count",
                )
            )
    return facts


def visual_facts(payload, evidence):
    # El servicio de insights sólo puede usar evidencia ya autorizada por data.
    known = {source_key(e): e for e in evidence}
    aliases = {}
    from inside_game.agents.contracts import Evidence

    for original in payload.get("evidence", []):
        parsed = Evidence.model_validate(original)
        key = source_key(parsed)
        if key not in known:
            raise ValueError("UNTRUSTED_VISUAL_EVIDENCE")
        aliases[parsed.evidence_id] = known[key]
    facts = []
    for block in payload.get("blocks", []):
        if block["state"] not in {"ready", "partial"}:
            continue
        sources = [aliases[key] for key in block["evidence_ids"] if key in aliases]
        if not sources:
            raise ValueError("VISUAL_WITHOUT_EVIDENCE")
        scope = {"visual_scopes": block["scope"], "block_id": block["id"]}
        for field in ("metrics", "by_team"):
            for f in scalar_facts(
                block.get(field, {}),
                sources[0],
                f"/blocks/{block['id']}/{field}",
                block_id=block["id"],
                scope=scope,
            ):
                facts.append(
                    f.model_copy(
                        update={"evidence_ids": [e.evidence_id for e in sources]}
                    )
                )
        if not block.get("metrics") and not block.get("by_team"):
            rows = block.get("rows", [])
            for index, row in enumerate(rows[:10]):
                for f in scalar_facts(
                    row,
                    sources[0],
                    f"/blocks/{block['id']}/rows/{index}",
                    block_id=block["id"],
                    scope={
                        **scope,
                        "table_rows": len(rows),
                        "rows_in_analysis": min(10, len(rows)),
                        "exhaustive": len(rows) <= 10,
                    },
                ):
                    facts.append(
                        f.model_copy(
                            update={"evidence_ids": [e.evidence_id for e in sources]}
                        )
                    )
    return facts


def display(fact):
    value = fact.value
    if type(value) in (int, float):
        if fact.label.endswith(("_rate", "_fraction")):
            return f"{value:.1%}"
        return (
            f"{value:.3f}".rstrip("0").rstrip(".")
            if isinstance(value, float)
            else str(value)
        )
    return value


def render_statement(statement, facts):
    by_id = {f.id: f for f in facts}
    if not set(statement.fact_ids) <= by_id.keys():
        raise ValueError("UNKNOWN_FACT_REFERENCE")
    tokens = TOKEN.findall(statement.text)
    if not set(tokens) <= set(statement.fact_ids):
        raise ValueError("PLACEHOLDER_REQUIRES_CITATION")
    stripped = TOKEN.sub("", statement.text)
    if re.search(r"\d", stripped) or "{{" in stripped or "}}" in stripped:
        raise ValueError("USE_FACT_PLACEHOLDERS_FOR_NUMBERS")
    validate_metric_labels(statement.text, by_id)
    validate_absolute_claims(stripped)
    if re.search(
        r"fase de (?:transición|progresión)|(?:presión|bloque) (?:alto|alta|medio|bajo)"
        r"|(?:high|mid|low) (?:press|block)|bloc (?:haut|médian|bas)|pression haute"
        r"|pressão alta|bloco (?:alto|médio|baixo)|blocco (?:alto|medio|basso)"
        r"|(?:hohes|tiefes) pressing|(?:hoher|tiefer) block",
        statement.text,
        re.IGNORECASE,
    ) and all(
        by_id[key].operation
        in {
            "get_team_shape",
            "get_proximity_connectivity",
            "get_space_coverage",
            "get_persistent_structure",
            "get_node_removal_robustness",
            "get_tracking_frame",
            "get_tracking_window",
        }
        for key in statement.fact_ids
    ):
        raise ValueError("UNSUPPORTED_TACTICAL_PHASE_FROM_GEOMETRY")
    rendered = TOKEN.sub(lambda m: display(by_id[m[1]]), statement.text)
    validate_score_claim(rendered, [by_id[key] for key in statement.fact_ids])
    return rendered


def validate_metric_labels(text, by_id):
    """Narrow cross-language guard against citing goals as shots or vice versa."""
    shots = r"(?:tiros?|remates?|disparos?|shots?|tirs?|finalizaç(?:ão|ões)|tiri|tiro|schüsse|schuss)"
    goals = r"(?:goles?|goals?|gols?|buts?|gol|tore?|tor)"
    for token in TOKEN.finditer(text):
        item = by_id.get(token[1])
        if item is None:
            continue
        following = text[token.end() :]
        if item.label in {"goals", "goal_count"} and re.match(
            r"\s+" + shots + r"\b", following, re.IGNORECASE
        ):
            raise ValueError("FACT_METRIC_LABEL_MISMATCH")
        if item.label in {"shots", "shot_count", "total_shots"} and re.match(
            r"\s+" + goals + r"\b", following, re.IGNORECASE
        ):
            raise ValueError("FACT_METRIC_LABEL_MISMATCH")


def validate_absolute_claims(text):
    """Reject specific unprovable guarantees, preserving scientific caveats.

    This lexical guard is not a general proof of semantic entailment.
    """
    for sentence in re.split(r"[.!?;]", text):
        if re.search(
            r"\b(?:no|not|never|cannot|can't|doesn't|don't|não|non|nicht|kein\w*)\b|ne .{0,60}\bpas\b",
            sentence,
            re.IGNORECASE,
        ):
            continue
        if re.search(
            r"impenetrab(?:le|les|ile|ili)|impénétrable|undurchdringlich"
            r"|(?:asegura|garantiza|garante|garantisce) (?:la |a )?(?:victoria|victória|vitória|vittoria)"
            r"|guarantees? (?:a |the )?(?:win|victory)|garantit la victoire|garantiert (?:den |einen )?sieg",
            sentence,
            re.IGNORECASE,
        ):
            raise ValueError("UNSUPPORTED_ABSOLUTE_CLAIM")


def validate_score_claim(text, cited):
    """Reject explicit winner/loser claims that contradict cited match scores.

    This is a narrow semantic guard, not a proof of every football inference.
    Group by match and evidence so a comparison cannot mix different scorelines.
    """
    groups = {}
    for item in cited:
        if item.operation == "get_match_context" and item.path.startswith(
            "/data/match/"
        ):
            key = (item.scope.get("match_id"), tuple(item.evidence_ids))
            groups.setdefault(key, {})[item.label] = item.value
    for values in groups.values():
        home, away = values.get("home_score"), values.get("away_score")
        if type(home) is not int or type(away) is not int:
            continue
        for side, margin, aliases in (
            ("home", home - away, ["el equipo local", "el local"]),
            ("away", away - home, ["el equipo visitante", "el visitante"]),
        ):
            name = values.get(side + "_team_name")
            if isinstance(name, str) and name:
                aliases.append(name)
            for alias in aliases:
                # Require match-result wording, not 'ganó espacio/un duelo'.
                pattern = (
                    r"(?<!\w)"
                    + re.escape(alias)
                    + r"\s+(ganó|venció|derrotó|perdió|cayó|empató)\s+"
                    + r"(?:por\s+)?(?:\d|el partido\b|frente\b|ante\b|contra\b|a\b)"
                )
                for claim in re.finditer(pattern, text, re.IGNORECASE):
                    expected = (
                        1
                        if claim[1].lower() in {"ganó", "venció", "derrotó"}
                        else -1
                        if claim[1].lower() in {"perdió", "cayó"}
                        else 0
                    )
                    actual = (margin > 0) - (margin < 0)
                    if expected != actual:
                        raise ValueError("MATCH_RESULT_CONTRADICTS_SCORE")


def reference_line(index, fact, *, language="es"):
    """Referencia de lectura; rutas y JSON completos permanecen en el sobre QA."""
    labels = {
        "players": "Jugadores de campo",
        "width_m": "Anchura",
        "length_m": "Longitud",
        "radius_of_gyration_m": "Dispersión alrededor del centro",
        "hull_area_m2": "Área de la envolvente",
        "hull_perimeter_m": "Perímetro de la envolvente",
        "epsilon_m": "Distancia de conexión",
        "component_count": "Grupos conectados",
        "largest_component_fraction": "Mayor grupo",
        "critical_connection_distance_m": "Distancia necesaria para conectar el conjunto",
        "h0": "Componentes (homología de dimensión cero)",
        "h1": "Ciclos (homología de dimensión uno)",
        "removed_player_id": "Jugador retirado virtualmente",
        "remaining_players": "Jugadores restantes en la simulación",
        "component_count_delta": "Variación del número de componentes",
        "birth_m": "Aparición del intervalo",
        "death_m": "Cierre del intervalo",
    }
    scope = fact.scope
    if scope.get("visual_scopes"):
        scope = scope["visual_scopes"][0]
    if language != "es":
        # Keep canonical metric keys in technical references; prose and headings
        # are localized. No translation is allowed to change a metric identity.
        details = {
            key: scope[key]
            for key in (
                "match_id",
                "team_id",
                "player_id",
                "period",
                "time_ms",
                "start_ms",
                "end_ms",
            )
            if key in scope
        }
        return (
            f"[{index}] {fact.label}: {display(fact)}"
            + (f" {fact.unit}" if fact.unit and fact.unit != "proporción" else "")
            + " · "
            + json.dumps(details, ensure_ascii=False, sort_keys=True)
        )
    details = []
    for key, label in [("match_id", "partido"), ("team_id", "equipo")]:
        if scope.get(key) is not None:
            details.append(f"{label} {scope[key]}")
    if scope.get("period") is not None:
        details.append(f"período {scope['period']}")
    if scope.get("time_ms") is not None:
        seconds = scope["time_ms"] // 1000
        details.append(f"{seconds // 60}:{seconds % 60:02d}")
    unit = "" if not fact.unit or fact.unit == "proporción" else " " + fact.unit
    label = labels.get(fact.label, fact.label)
    if fact.label.startswith("team_area_m2."):
        label = "Área Voronoi del equipo " + fact.label.rsplit(".", 1)[-1]
    return f"[{index}] {label}: {display(fact)}{unit} · " + ", ".join(details)
