"""Qué puede mostrar cada fuente, medido con scripts/insights_availability.py.

Un perfil se mide con un partido por fuente y se aplica a toda la fuente: es una
generalización explícita, no una garantía por partido. Las recetas `partial` se
conservan porque el bloque declara su denominador.
"""

import json
from pathlib import Path

from inside_game.insights.labels import clean_key

PROFILE_FILE = Path(__file__).with_name("source_profiles.json")


def source_key(match):
    return (
        "synthetic" if match.get("is_synthetic") else match.get("provider") or "unknown"
    )


def load_profiles(path=PROFILE_FILE):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def zero_only(row):
    """`ready` sin elementos dibujables y con todas las métricas en cero o nulas."""
    metrics = row.get("metrics") or {}
    return (
        row["state"] == "ready"
        and not row.get("items")
        and bool(metrics)
        and all(v in (0, None) for v in metrics.values())
    )


# Recetas cuyas cifras son recuentos de lo que la fuente anota; en las demás un
# cero puede ser un valor calculado (errores numéricos, fracciones).
EVENT_RECIPES = {
    "shot_map",
    "xg_story",
    "pass_map",
    "defensive_actions",
    "pressure_recovery",
    "ball_progression",
    "zone_presence",
}


def unannotated_by_source(report, minimum_matches=2):
    """Métricas en cero en todos los partidos medidos de una fuente (por receta).

    Si ninguna acción de ese tipo aparece en ningún partido, la fuente no la anota.
    Se exige un mínimo de partidos: con uno solo no se distingue de un cero real.
    """
    by_source = {}
    for match in report["matches"]:
        by_source.setdefault(source_key(match), []).append(match)
    result = {}
    for source, matches in by_source.items():
        recipes = {}
        if len(matches) >= minimum_matches:
            for insight_id in matches[0]["insights"]:
                if insight_id not in EVENT_RECIPES:
                    continue
                rows = [m["insights"].get(insight_id, {}) for m in matches]
                if not all(r.get("state") == "ready" for r in rows):
                    continue
                keys = {clean_key(k) for r in rows for k in (r.get("metrics") or {})}
                keys.discard("total")
                zero = sorted(
                    k
                    for k in keys
                    if all(
                        v in (0, None)
                        for r in rows
                        for kk, v in (r.get("metrics") or {}).items()
                        if clean_key(kk) == k
                    )
                )
                if zero:
                    recipes[insight_id] = zero
        result[source] = recipes
    return result


def build_profiles(report):
    """Matriz de disponibilidad → recetas imposibles o engañosas por fuente."""
    profiles = {}
    for match in report["matches"]:
        unavailable, misleading = {}, {}
        for insight_id, row in match["insights"].items():
            reason = " ".join(row.get("reasons") or row.get("api_errors") or [])
            if row["state"] in {"unavailable", "no_evidence", "spec_rejected", "error"}:
                unavailable[insight_id] = reason or row["state"]
            elif zero_only(row):
                misleading[insight_id] = (
                    "La fuente no anota estas acciones; el bloque mostraría ceros "
                    "que no significan ausencia."
                )
        profiles[source_key(match)] = {
            "measured_match_id": match["match_id"],
            "unavailable": unavailable,
            "zero_only": misleading,
        }
    unannotated = unannotated_by_source(report)
    for source, recipes in unannotated.items():
        if source in profiles:
            profiles[source]["unannotated_metrics"] = recipes
    return profiles
