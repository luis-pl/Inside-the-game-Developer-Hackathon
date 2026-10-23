"""Aplica emisión/revocación y fuerza una nueva revisión que recarga el registro.

Revocar en el archivo privado no modifica Azure hasta ejecutar este comando y
verificar que la nueva revisión está activa. Nunca publica las claves originales.
"""

import argparse
import json
import uuid
from pathlib import Path

from azure_runtime import ROOT, azure, save_state
from manage_credentials import registry_from_private


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-file", type=Path, required=True)
    args = parser.parse_args()
    state = json.loads((ROOT / "deployment/cloud.json").read_text(encoding="utf-8"))
    records = registry_from_private(args.private_file)
    if not any(r["enabled"] and r["role"] == "developer" for r in records):
        parser.error("Keep at least one enabled developer credential")
    azure(
        "containerapp",
        "secret",
        "set",
        "-g",
        state["resource_group"],
        "-n",
        state["app_name"],
        "--secrets",
        "individual-credentials=" + json.dumps(records, separators=(",", ":")),
    )
    app = azure(
        "containerapp",
        "update",
        "-g",
        state["resource_group"],
        "-n",
        state["app_name"],
        "--set-env-vars",
        "INSIDE_GAME_CREDENTIALS_VERSION=" + uuid.uuid4().hex,
    )
    state["revision"] = app["properties"].get("latestReadyRevisionName")
    save_state(state)
    print(
        json.dumps(
            {
                "revision": state["revision"],
                "enabled_ids": [r["id"] for r in records if r["enabled"]],
            }
        )
    )


if __name__ == "__main__":
    main()
