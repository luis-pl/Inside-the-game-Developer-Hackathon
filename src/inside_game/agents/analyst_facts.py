"""Hechos de fuentes y métricas del renderer; el LLM no puede crear sus valores."""

import hashlib
import json
import re
from math import isfinite

from inside_game.agents.analyst_contracts import Fact

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
    for ev in evidence:
        data = ev.response.data
        for key in ("summary", "metrics", "match"):
            facts.extend(scalar_facts(data.get(key, {}), ev, "/data/" + key))
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
        for i, sample in enumerate(data.get("samples", [])):
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
    if re.search(
        r"fase de (?:transición|progresión)|(?:presión|bloque) (?:alto|alta|medio|bajo)",
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
    return TOKEN.sub(lambda m: display(by_id[m[1]]), statement.text)


def reference_line(index, fact):
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
