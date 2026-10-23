"""Emite o revoca claves de demo; el archivo privado debe quedar fuera del repo.

La salida estándar contiene sólo IDs y rutas. Los tokens se leen directamente
del archivo privado para configurar clientes; nunca se copian a logs o Git.
El registro derivado de SHA256 es la única información enviada al servidor.
"""

import argparse
import hashlib
import json
import re
import secrets
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def registry_from_private(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        {
            "id": c["id"],
            "name": c["name"],
            "role": c["role"],
            "sha256": hashlib.sha256(c["key"].encode()).hexdigest(),
            "expires_at": c["expires_at"],
            "enabled": c.get("enabled", True),
            **({"operations": c["operations"]} if "operations" in c else {}),
        }
        for c in data["credentials"]
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-file", required=True, type=Path)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--create", action="store_true")
    actions.add_argument("--revoke")
    actions.add_argument("--issue-id")
    parser.add_argument("--name")
    parser.add_argument("--role", choices=("developer", "agent"), default="developer")
    parser.add_argument("--days", type=int, default=14)
    args = parser.parse_args()
    path = args.private_file.resolve()
    if path == ROOT or ROOT in path.parents:
        parser.error("Credentials must be stored outside the repository")
    if not path.parent.is_dir() or not 1 <= args.days <= 30:
        parser.error(
            "Create a private parent directory first; validity must be 1..30 days"
        )
    if args.create:
        if path.exists():
            parser.error("Refusing to overwrite existing credentials")
        now = int(time.time())
        data = {
            "created_at": now,
            "credentials": [
                {
                    "id": id,
                    "name": name,
                    "role": role,
                    "enabled": True,
                    "expires_at": now + args.days * 86400,
                    "key": "ig_" + role + "_" + secrets.token_urlsafe(48),
                }
                for id, name, role in (
                    ("team-owner", "Responsable del equipo", "developer"),
                    ("team-collaborator-01", "Companero autorizado 01", "developer"),
                    ("agent-data", "Agente de datos", "agent"),
                )
            ],
        }
        with path.open("x", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    elif args.issue_id:
        if not re.fullmatch(r"[a-z0-9-]{1,80}", args.issue_id):
            parser.error(
                "Use a credential ID of 1..80 lowercase letters, digits or hyphens"
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        if len(data["credentials"]) >= 100 or any(
            c["id"] == args.issue_id for c in data["credentials"]
        ):
            parser.error("Credential ID already exists or registry is full")
        name = args.name or args.issue_id
        if not 1 <= len(name) <= 100:
            parser.error("Credential name must contain 1..100 characters")
        data["credentials"].append(
            {
                "id": args.issue_id,
                "name": name,
                "role": args.role,
                "enabled": True,
                "expires_at": int(time.time()) + args.days * 86400,
                "key": "ig_" + args.role + "_" + secrets.token_urlsafe(48),
            }
        )
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    elif args.revoke:
        data = json.loads(path.read_text(encoding="utf-8"))
        matches = [c for c in data["credentials"] if c["id"] == args.revoke]
        if len(matches) != 1:
            parser.error("Credential ID not found")
        matches[0]["enabled"] = False
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    else:
        parser.error("Use --create or --revoke ID")
    print(
        json.dumps(
            {
                "private_file": str(path),
                "credential_ids": [c["id"] for c in data["credentials"]],
            }
        )
    )


if __name__ == "__main__":
    main()
