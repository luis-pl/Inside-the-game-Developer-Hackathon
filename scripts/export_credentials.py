"""Prepara un archivo privado por titular para evitar compartir todas las claves.

Se ejecuta en la máquina administradora. Las salidas deben seguir fuera del repo
y en una carpeta con ACL privada. No entrega correos ni imprime las claves.
"""

import argparse
import json
import re
from pathlib import Path

from azure_runtime import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-file", required=True, type=Path)
    args = parser.parse_args()
    path = args.private_file.resolve()
    if ROOT in path.parents:
        parser.error("Private credentials cannot reside inside the repository")
    data = json.loads(path.read_text(encoding="utf-8"))
    state = json.loads((ROOT / "deployment/cloud.json").read_text(encoding="utf-8"))
    files = []
    for credential in data["credentials"]:
        if not re.fullmatch(r"[a-z0-9-]{1,80}", credential["id"]):
            parser.error("Credential ID is not a safe filename")
        target = path.parent / (credential["id"] + ".json")
        if target.exists():
            parser.error("Refusing to overwrite an exported credential")
        handoff = {
            "credential_id": credential["id"],
            "role": credential["role"],
            "api_url": state["url"],
            "mcp_url": state["url"] + "/mcp",
            "key": credential["key"],
            "expires_at": credential["expires_at"],
            "authorization_header": "Bearer (use the key field)",
        }
        if credential["id"] == "team-collaborator-01":
            handoff["assigned_to"] = "Soyturistalvlx@hotmail.com"
            handoff["identity_verification"] = (
                "Assigned by the project owner; mailbox not independently verified"
            )
        target.write_text(json.dumps(handoff, indent=2) + "\n", encoding="utf-8")
        files.append(str(target))
    print(json.dumps({"private_handoff_files": files}))


if __name__ == "__main__":
    main()
