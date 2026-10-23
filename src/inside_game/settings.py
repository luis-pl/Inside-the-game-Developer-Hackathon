"""Configuration is server-owned; request bodies cannot override it."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    server: str = "sql-inside-game-01a160e1-ca.database.windows.net"
    database: str = "inside-game"
    reader_user: str = "inside_game_api_reader"
    api_key: str = ""
    local_access: bool = True
    rate_per_minute: int = 120
    max_concurrent: int = 4
    cache_seconds: int = 300
    allowed_matches: tuple[int, ...] = tuple(range(900001, 900011))

    @classmethod
    def from_env(cls):
        return cls(
            server=os.getenv("INSIDE_GAME_SQL_SERVER", cls.server),
            database=os.getenv("INSIDE_GAME_SQL_DATABASE", cls.database),
            reader_user=os.getenv("INSIDE_GAME_SQL_READER", cls.reader_user),
            api_key=os.getenv("INSIDE_GAME_API_KEY", ""),
            local_access=os.getenv("INSIDE_GAME_LOCAL_ACCESS", "true").lower()
            == "true",
            allowed_matches=tuple(
                int(v)
                for v in os.getenv(
                    "INSIDE_GAME_MATCH_IDS", ",".join(map(str, cls.allowed_matches))
                ).split(",")
                if v
            ),
        )
