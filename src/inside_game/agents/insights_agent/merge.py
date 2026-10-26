"""Acumula en un solo informe lo que se pide en una conversación sobre un partido.

Si la persona sigue preguntando por los mismos equipos, la página no se
reemplaza: las piezas nuevas se suman a las anteriores. Un partido o equipos
distintos empiezan un informe nuevo. Sólo reordena referencias de evidencia
(los IDs de cada petición chocan entre sí); no cambia cifras ni crea texto.
"""

import copy
import json

CONTEXT = "get_match_context"


def match_of(manifest):
    """(partido, equipo local, equipo visitante) según el contexto de la evidencia."""
    for evidence in manifest.get("evidence", []):
        if evidence.get("operation") == CONTEXT:
            match = evidence["response"]["data"].get("match", {})
            return (
                match.get("match_id"),
                match.get("home_team_id"),
                match.get("away_team_id"),
            )
    return None


def _context_ids(manifest):
    return [e["evidence_id"] for e in manifest["evidence"] if e["operation"] == CONTEXT]


def _signature(block):
    return (
        block["insight_id"],
        json.dumps(block.get("parameters") or {}, sort_keys=True, default=str),
    )


def _unique(value, taken, suffix):
    candidate = value
    while candidate in taken:
        candidate = f"{candidate}-{suffix}"
        suffix += 1
    return candidate


def merge_manifests(previous, new, turn):
    """Manifiesto combinado y cuántas piezas se añadieron, o None si no procede.

    `turn` numera la petición (2 para la primera ampliación) y prefija los IDs de
    evidencia nuevos para que no choquen con los anteriores.
    """
    if not previous or not new:
        return None
    key = match_of(previous)
    if key is None or key != match_of(new) or key[0] is None:
        return None
    merged = copy.deepcopy(previous)
    shown = {_signature(b) for b in merged["blocks"]}
    own_context = _context_ids(merged)
    prefix = f"t{turn}-"
    taken_ids = {b["id"] for b in merged["blocks"]}
    taken_titles = {b.get("title") for b in merged["blocks"]}

    remap = {}
    for evidence in new["evidence"]:
        old_id = evidence["evidence_id"]
        if evidence["operation"] == CONTEXT and own_context:
            remap[old_id] = own_context[0]
            continue
        evidence = copy.deepcopy(evidence)
        evidence["evidence_id"] = remap[old_id] = prefix + old_id
        merged["evidence"].append(evidence)

    added, fresh = 0, []
    for block in new["blocks"]:
        signature = _signature(block)
        if signature in shown:
            continue
        block = copy.deepcopy(block)
        if any(i not in remap for i in block["evidence_ids"]):
            return None
        block["evidence_ids"] = list(
            dict.fromkeys(remap[i] for i in block["evidence_ids"])
        )
        block["id"] = _unique(block["id"], taken_ids, turn)
        title = block.get("title")
        if title in taken_titles:
            period = (block.get("parameters") or {}).get("period")
            block["title"] = (
                f"{title} · {period}.ª parte" if period else f"{title} ({turn})"
            )
        taken_ids.add(block["id"])
        taken_titles.add(block.get("title"))
        shown.add(signature)
        fresh.append(block)
        added += 1
    if not added:
        return copy.deepcopy(previous), 0
    # Lo último que se pidió, arriba: es lo que la persona quiere ver primero.
    merged["blocks"] = fresh + merged["blocks"]
    # Sin evidencia sobrante de una pieza que no se añadió.
    used = {i for b in merged["blocks"] for i in b["evidence_ids"]}
    merged["evidence"] = [
        e
        for e in merged["evidence"]
        if e["evidence_id"] in used or e["operation"] == CONTEXT
    ]
    merged["template_id"] = "custom_report"
    return merged, added
