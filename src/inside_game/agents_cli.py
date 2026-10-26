"""Inicia el HTTP de agentes. Configuración privada del anfitrión, sin eval."""

import argparse
import hashlib
import json
import os
from pathlib import Path

from inside_game.agents.http_api import create_agent_app


def load_local_env(root):
    values = {}
    for name in (".env", ".env.local"):
        path = root / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip().startswith(("INSIDE_GAME_", "AZURE_")):
                values[key.strip()] = value.strip().strip("\"'")
    for key, value in values.items():
        os.environ.setdefault(key, value)


def app_from_env(port=8085):
    records = json.loads(os.getenv("INSIDE_GAME_AGENT_CREDENTIALS_JSON", "[]"))
    if not records:
        # Se permite reutilizar exclusivamente la credencial individual agent-data
        # ya autorizada. No se lee un registro administrativo de claves privadas.
        path = os.getenv("INSIDE_GAME_DATA_MCP_CREDENTIAL_FILE", "")
        entry = json.loads(Path(path).read_text(encoding="utf-8")) if path else {}
        if entry.get("credential_id") != "agent-data":
            raise ValueError("INDIVIDUAL_AGENT_CREDENTIAL_REQUIRED")
        records = [
            {
                "id": entry["credential_id"],
                "name": "Data agent",
                "role": "agent",
                "expires_at": entry["expires_at"],
                "sha256": hashlib.sha256(entry["key"].encode()).hexdigest(),
            }
        ]
    hosts = os.getenv("INSIDE_GAME_AGENT_ALLOWED_HOSTS", "localhost,127.0.0.1").split(
        ","
    )
    return create_agent_app(
        credentials=records,
        data_base_url=os.getenv(
            "INSIDE_GAME_DATA_AGENT_URL", f"http://127.0.0.1:{port}"
        ),
        allowed_hosts=tuple(hosts),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8085)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    load_local_env(root)
    try:
        app = app_from_env(args.port)
    except (ValueError, OSError, KeyError):
        parser.exit(
            1,
            "Configura credenciales individuales del HTTP de agentes. No compartas sus valores.\n",
        )
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, access_log=False)


if __name__ == "__main__":
    main()
