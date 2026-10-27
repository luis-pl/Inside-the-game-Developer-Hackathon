"""QA del BFF local: creación, modificación y xG ausente. Nunca registra cookies."""

import argparse
import json
import time
from pathlib import Path
from uuid import uuid4

import httpx


def run(folder=Path(".temp/workspace-qa")):
    folder.mkdir(parents=True, exist_ok=True)
    with httpx.Client(
        base_url="http://127.0.0.1:8090",
        trust_env=False,
        timeout=60,
        headers={"X-Inside-Game": "workspace"},
    ) as client:
        client.post("/workspace-api/session").raise_for_status()
        catalog = client.get("/workspace-api/chat-catalog")
        catalog.raise_for_status()
        matches = catalog.json()["matches"]
        (folder / "matches.json").write_text(
            json.dumps(matches, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        cid = client.post("/workspace-api/conversations").json()["id"]

        def send(name, text, context):
            body = {"request_id": str(uuid4()), "text": text, "context": context}
            (folder / (name + ".request.json")).write_text(
                json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            r = client.post(f"/workspace-api/conversations/{cid}/messages", json=body)
            r.raise_for_status()
            deadline = time.monotonic() + 120
            previous = None
            while time.monotonic() < deadline:
                response = client.get(f"/workspace-api/conversations/{cid}")
                response.raise_for_status()
                value = response.json()
                if value["stage"] != previous:
                    print(
                        json.dumps(
                            {"case": name, "stage": value["stage"]}, ensure_ascii=False
                        ),
                        flush=True,
                    )
                    previous = value["stage"]
                if not value["busy"]:
                    (folder / (name + ".json")).write_text(
                        json.dumps(value, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    if value["report"]:
                        page = client.get(f"/workspace-api/conversations/{cid}/page")
                        page.raise_for_status()
                        (folder / (name + ".html")).write_text(
                            page.text, encoding="utf-8"
                        )
                    return value
                time.sleep(3)
            raise TimeoutError("WORKSPACE_QA_DEADLINE")

        first = send(
            "create",
            "Muéstrame en una página los tiros de ambos equipos y cómo fue creciendo su xG. Usa los nombres de los equipos y explícame lo más importante en pocas palabras.",
            {"match_ids": [900001]},
        )
        assert first["stage"] == "complete" and len(first["report"]["blocks"]) == 2, (
            first["runs"][-1].get("error")
        )
        report_id = first["report"]["report_id"]
        assert not first["messages"][-1]["content"].startswith("Creé la página"), (
            "SPORTS_REPLY_MISSING"
        )
        edited = send(
            "modify",
            "En la página actual cambia únicamente el título a «Ocasiones bajo la lupa». Conserva los dos gráficos, su evidencia y sus colores.",
            first["context"],
        )
        assert (
            edited["stage"] == "complete" and edited["report"]["report_id"] == report_id
        )
        assert (
            edited["report"]["revision"] > first["report"]["revision"]
            and len(edited["report"]["blocks"]) == 2
        )
        cid = client.post("/workspace-api/conversations").json()["id"]
        unsupported = send(
            "missing-xg",
            "Quiero el xG de este partido real Metrica. Si no está disponible explícamelo sin inventarlo.",
            {"match_ids": [900011]},
        )
        assert (
            unsupported["stage"] in {"clarification", "complete"}
            and unsupported["report"] is None
        )
        assert unsupported["runs"][-1]["delegation"]["action"] in {"clarify", "answer"}
        assert (
            "no tiene xg" in unsupported["messages"][-1]["content"].casefold()
            or "no hay" in unsupported["messages"][-1]["content"].casefold()
        )
        result = {
            "passed": True,
            "create": first["id"],
            "modify_revision": edited["report"]["revision"],
            "missing_xg": unsupported["stage"],
            "catalog_matches": len(matches),
        }
        (folder / "verification.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path(".temp/workspace-qa"))
    run(parser.parse_args().output_dir)
