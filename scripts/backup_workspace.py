"""Conserva las conversaciones e informes del titular local antes de reiniciar."""

import argparse
from pathlib import Path

from inside_game.agents_cli import app_from_env, load_local_env
from inside_game.tools.mcp_client import DataMcpSettings
from inside_game.workspace_snapshot import export_snapshot

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path(".temp/workspace-user-backup.json")
    )
    args = parser.parse_args()
    load_local_env(Path(__file__).resolve().parents[1])
    settings = DataMcpSettings.from_env()
    principal = app_from_env().state.registry.verify(settings.key)
    print(
        export_snapshot(
            "http://127.0.0.1:8090", settings.key, principal.id, args.output
        )
    )
