"""Un bloque consume las páginas recibidas de su misma consulta, sin ampliar filtros."""

import json


def include_query_pages(plan, evidence):
    def key(e):
        return json.dumps(
            [
                e.query_id,
                e.operation,
                {k: v for k, v in e.arguments.items() if k not in {"cursor", "limit"}},
                e.response.provenance,
            ],
            sort_keys=True,
        )

    by_id = {e.evidence_id: e for e in evidence}
    groups = {}
    for e in evidence:
        groups.setdefault(key(e), []).append(e.evidence_id)
    blocks = []
    for block in plan.blocks:
        ids = list(block.evidence_ids)
        for eid in block.evidence_ids:
            if eid in by_id:
                ids.extend(groups[key(by_id[eid])])
        blocks.append(
            block.model_copy(update={"evidence_ids": list(dict.fromkeys(ids))})
        )
    return plan.model_copy(update={"blocks": blocks}, deep=True)
