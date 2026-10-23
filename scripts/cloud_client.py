"""Consulta la API remota sin imprimir la clave leída del archivo privado.

Ejemplo: python scripts/cloud_client.py --private-file RUTA --identity agent-data
"""

import argparse
import json
from pathlib import Path

import httpx
from azure_runtime import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-file", type=Path, required=True)
    parser.add_argument("--identity", default="team-owner")
    parser.add_argument("--operation", default="get_shots")
    parser.add_argument(
        "--body",
        default='{"match_id":900001,"team_id":1,"outcome":"on_target","view":"summary"}',
    )
    args = parser.parse_args()
    state = json.loads((ROOT / "deployment/cloud.json").read_text(encoding="utf-8"))
    credentials = json.loads(args.private_file.read_text(encoding="utf-8"))[
        "credentials"
    ]
    credential = next(c for c in credentials if c["id"] == args.identity)
    with httpx.Client(
        base_url=state["url"],
        headers={"Authorization": "Bearer " + credential["key"]},
        timeout=90,
        trust_env=False,
    ) as client:
        response = client.post(
            "/api/operations/" + args.operation, json=json.loads(args.body)
        )
        print(
            json.dumps(
                {"status_code": response.status_code, "response": response.json()},
                ensure_ascii=False,
                indent=2,
            )
        )
        response.raise_for_status()


if __name__ == "__main__":
    main()
