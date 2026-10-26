"""Configuración local del proceso: entorno o archivos .env privados del repo.

Nunca lee argumentos de línea ni cuerpos de petición; los valores no se
registran. Los procesos de servidor y los scripts comparten esta lectura.
"""

import os


def local_setting(name, root):
    """Variable de entorno o de `.env.local`/`.env` en `root`; vacío si no existe."""
    if os.environ.get(name):
        return os.environ[name]
    for filename in (".env.local", ".env"):
        file = root / filename
        if file.exists():
            for line in file.read_text(encoding="utf-8-sig").splitlines():
                key, sep, value = line.partition("=")
                if sep and key.strip() == name:
                    return value.strip().strip("\"'")
    return ""


def load_local_env(root, prefix="INSIDE_GAME_"):
    """Copia al entorno del proceso las variables `prefix*` de `.env.local`/`.env`.

    Igual que scripts/start-data-agent.ps1: sólo asignaciones, sin evaluar nada,
    y sin pisar lo que ya esté en el entorno. Así el proveedor del modelo, que
    lee el entorno, ve la configuración privada del repo.
    """
    for filename in (".env.local", ".env"):
        file = root / filename
        if not file.exists():
            continue
        for line in file.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.partition("=")
            key = key.strip()
            if sep and key.startswith(prefix) and key not in os.environ:
                os.environ[key] = value.strip().strip("\"'")
