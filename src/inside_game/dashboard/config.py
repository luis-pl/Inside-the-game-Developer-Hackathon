"""Server-side configuration; never exposes environment values to the browser."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class DashboardConfig:
    api_url: str
    api_key: str = field(repr=False)

    @classmethod
    def load(cls, root: Path):
        values = {}
        for filename in (".env", ".env.local"):
            file = root / filename
            if file.exists():
                for line in file.read_text(encoding="utf-8-sig").splitlines():
                    name, sep, value = line.partition("=")
                    if sep and name.strip().startswith("INSIDE_GAME_"):
                        values[name.strip()] = value.strip().strip("\"'")
        values.update(
            {k: v for k, v in os.environ.items() if k.startswith("INSIDE_GAME_")}
        )
        url = (
            values.get("INSIDE_GAME_API_URL")
            or values.get("INSIDE_GAME_MCP_API_URL")
            or values.get("INSIDE_GAME_DATA_MCP_URL", "")
        )
        parsed = urlsplit(url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "Configura INSIDE_GAME_API_URL como una URL sin credenciales."
            )
        if parsed.scheme != "https" and parsed.hostname not in (
            "127.0.0.1",
            "localhost",
            "::1",
        ):
            raise ValueError("La API remota debe usar HTTPS.")
        return cls(
            f"{parsed.scheme}://{parsed.netloc}", values.get("INSIDE_GAME_API_KEY", "")
        )
