"""Prueba trazada de una actualización solicitada, conservando los bloques previos."""

import argparse
import json
import time
from pathlib import Path
from uuid import uuid4

import httpx


def run(cid, folder):
    folder.mkdir(parents=True, exist_ok=True)

    def save(name, value):
        (folder / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    with httpx.Client(
        base_url="http://127.0.0.1:8090",
        headers={"X-Inside-Game": "workspace"},
        trust_env=False,
        timeout=60,
    ) as client:
        client.post("/workspace-api/session").raise_for_status()
        before = client.get("/workspace-api/conversations/" + cid)
        before.raise_for_status()
        before = before.json()
        save("before.json", before)
        body = {
            "request_id": str(uuid4()),
            "text": "añade el xg y dime quien fue el jugador estrella",
            "context": before["report_context"],
        }
        save("request.json", body)
        result = client.post(f"/workspace-api/conversations/{cid}/messages", json=body)
        result.raise_for_status()
        previous = None
        start = time.monotonic()
        while time.monotonic() - start < 125:
            response = client.get("/workspace-api/conversations/" + cid)
            response.raise_for_status()
            state = response.json()
            if state["stage"] != previous:
                print(
                    json.dumps(
                        {
                            "stage": state["stage"],
                            "seconds": round(time.monotonic() - start, 1),
                        }
                    ),
                    flush=True,
                )
                previous = state["stage"]
            if not state["busy"]:
                save("after.json", state)
                page = client.get(f"/workspace-api/conversations/{cid}/page")
                page.raise_for_status()
                (folder / "updated.html").write_text(page.text, encoding="utf-8")
                old = {b["id"] for b in before["report"]["blocks"]}
                new = {b["id"] for b in state["report"]["blocks"]}
                assert old <= new, "PREVIOUS_BLOCKS_REMOVED"
                result = {
                    "stage": state["stage"],
                    "seconds": round(time.monotonic() - start, 2),
                    "old_blocks": len(old),
                    "new_blocks": len(new),
                    "preserved": True,
                    "recipes": [b["insight_id"] for b in state["report"]["blocks"]],
                    "error": state["runs"][-1].get("error"),
                    "changes": state.get("changes"),
                }
                save("verification.json", result)
                print(json.dumps(result, ensure_ascii=False), flush=True)
                run = state["runs"][-1]
                scoped = (
                    state["stage"] == "partial"
                    and run.get("insights", {}).get("status") == "complete"
                    and (run.get("analysis") or {}).get("status") == "partial"
                    and not (run.get("analysis") or {}).get("issues")
                )
                assert state["stage"] == "complete" or scoped, "UPDATE_NOT_COMPLETE"
                assert all(b["state"] == "ready" for b in state["report"]["blocks"]), (
                    "GRAPH_DATA_NOT_READY"
                )
                assert {"xg_story", "entity_comparison"} <= set(result["recipes"])
                return
            time.sleep(3)
        raise TimeoutError("QA_DEADLINE")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--conversation-id", required=True)
    p.add_argument("--output-dir", type=Path, default=Path(".temp/ux-qa"))
    args = p.parse_args()
    run(args.conversation_id, args.output_dir)
