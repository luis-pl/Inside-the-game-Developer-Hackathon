"""Respaldo explícito de la demo local, sin credenciales y sin repetir trabajos."""

import hashlib
import json
import time
from pathlib import Path
from uuid import UUID

import httpx

from inside_game.agents.analyst_facts import source_key
from inside_game.agents.contracts import DataContext, Evidence
from inside_game.agents.insight_contracts import InsightResult
from inside_game.agents.insights_http_client import PayloadParser
from inside_game.agents.report_store import Snapshot
from inside_game.insights.contracts import ReportPlan, ReportSpec


def export_snapshot(base_url, key, owner, path):
    items = []
    with httpx.Client(
        base_url=base_url,
        headers={"Authorization": "Bearer " + key},
        timeout=20,
        trust_env=False,
        follow_redirects=False,
    ) as client:
        listing = client.get("/a2a/v1/conversations")
        listing.raise_for_status()
        for row in listing.json():
            response = client.get("/a2a/v1/conversations/" + row["id"])
            response.raise_for_status()
            state = response.json()
            if state["busy"]:
                raise ValueError("WAIT_FOR_RUNNING_CONVERSATION")
            saved = None
            if state["report"]:
                rid = state["report"]["report_id"]
                meta = client.get("/a2a/v1/reports/" + rid)
                if meta.status_code == 200:
                    metadata = meta.json()
                    html = client.get(metadata["artifact_url"])
                    html.raise_for_status()
                    saved = {"metadata": metadata, "html": html.text}
            items.append({"conversation": state, "snapshot": saved})
    payload = {"version": 1, "owner": owner, "items": items}
    encoded = json.dumps(payload, ensure_ascii=False)
    if key in encoded:
        raise ValueError("SECRET_IN_SNAPSHOT")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(encoded, encoding="utf-8")
    return {
        "conversations": len(items),
        "reports": sum(bool(i["snapshot"]) for i in items),
    }


def restore_snapshot(agent_app, path, key):
    path = Path(path)
    if path.stat().st_size > 128 * 1024 * 1024:
        raise ValueError("SNAPSHOT_TOO_LARGE")
    principal = agent_app.state.registry.verify(key)
    data = json.loads(path.read_text(encoding="utf-8"))
    if (
        not principal
        or data.get("owner") != principal.id
        or data.get("version") != 1
        or len(data["items"]) > 20
    ):
        raise ValueError("SNAPSHOT_OWNER_MISMATCH")
    restored = []
    for item in data["items"]:
        state = item["conversation"]
        UUID(state["id"])
        if state["busy"]:
            raise ValueError("SNAPSHOT_HAS_RUNNING_JOB")
        saved = item["snapshot"]
        if saved:
            meta = saved["metadata"]
            parser = PayloadParser()
            parser.feed(saved["html"])
            payload = json.loads("".join(parser.parts))
            evidence = [Evidence.model_validate(e) for e in payload["evidence"]]
            hashes = {
                e.evidence_id: hashlib.sha256(source_key(e).encode()).hexdigest()
                for e in evidence
            }
            catalog_hashes = {
                e["evidence_id"]: e["source_sha256"] for e in meta["evidence_catalog"]
            }
            # El HTML contiene la evidencia usada por el informe; el almacén puede
            # conservar consultas adicionales que ningún bloque referencia.
            # Cada fuente restaurada debe coincidir exactamente; ReportSpec exige
            # después que estén presentes todas las referencias del plan.
            if any(catalog_hashes.get(eid) != digest for eid, digest in hashes.items()):
                raise ValueError("SNAPSHOT_EVIDENCE_MISMATCH")
            plan = ReportPlan.model_validate(meta["plan"])
            ReportSpec(**plan.model_dump(mode="json"), evidence=evidence)
            result = InsightResult.model_validate(
                {k: v for k, v in meta.items() if k in InsightResult.model_fields}
            )
            result = result.model_copy(
                update={"html": saved["html"], "plan": plan, "evidence": evidence}
            )
            context = DataContext.model_validate(state["report_context"])
            state["report"].update(
                revision=result.revision, blocks=result.blocks, status=result.status
            )
            restored.append((state, result, context))
        else:
            state["report"] = None
            restored.append((state, None, None))
    # Validar todo antes de incorporar cualquier conversación o informe.
    for state, result, context in restored:
        state["expires"] = time.monotonic() + 3600
        agent_app.state.chat.items[principal.id, state["id"]] = state
        if result:
            agent_app.state.store.pages[principal.id, str(result.report_id)] = {
                "versions": {result.revision: Snapshot(result, context)},
                "expires": time.monotonic() + 3600,
            }
    return len(restored)
