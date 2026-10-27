"""Cambios verificables de un plan; el modelo no decide qué se resalta en la UI."""

import hashlib
import json


def block_signature(block):
    return block.model_dump(mode="json", exclude={"title", "visual", "layout"})


def describe_changes(previous, current):
    before = {b.id: b for b in previous.blocks} if previous else {}
    after = {b.id: b for b in current.blocks}

    def item(block):
        return {
            "id": block.id,
            "title": block.title or block.insight_id,
            "insight_id": block.insight_id,
        }

    return {
        "added": [item(b) for bid, b in after.items() if bid not in before],
        "updated": [
            item(b) for bid, b in after.items() if bid in before and b != before[bid]
        ],
        "removed": [item(b) for bid, b in before.items() if bid not in after],
        "data_changed_ids": [
            b.id
            for b in current.blocks
            if b.id not in before or block_signature(b) != block_signature(before[b.id])
        ],
        "title_changed": bool(previous and previous.title != current.title),
        "analysis_updated": bool(
            current.analyst and (not previous or current.analyst != previous.analyst)
        ),
        "id": hashlib.sha256(
            json.dumps(current.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()[:16],
    }
