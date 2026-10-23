"""Invoca la CLI portable sin cmd.exe y sin imprimir comandos con secretos."""

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def azure(*args, timeout=1800):
    path = Path(os.environ["AZURE_CLI_PATH"]).resolve()
    python = path.parents[1] / "python.exe"
    command = [
        str(python),
        "-IBm",
        "azure.cli",
        *map(str, args),
        "--only-show-errors",
        "-o",
        "json",
    ]
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if result.returncode:
        # Los errores de CLI pueden contener los argumentos originales. Los
        # comandos que llevan secretos reciben un diagnóstico genérico.
        secret = "--secrets" in args or "--logs-workspace-key" in args
        detail = (
            "Azure command with secret inputs failed; inspect resource status"
            if secret
            else result.stderr[-4000:]
        )
        raise RuntimeError(detail)
    return json.loads(result.stdout) if result.stdout.strip() else None


def save_state(data):
    directory = ROOT / "deployment"
    directory.mkdir(exist_ok=True)
    (directory / "cloud.json").write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )
