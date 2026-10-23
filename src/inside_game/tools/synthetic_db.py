"""Azure SQL access through packaged SELECT templates and a read-only context."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import date, datetime
from datetime import time as daytime
from decimal import Decimal
from importlib.resources import files
from types import SimpleNamespace
from uuid import UUID

from inside_game.errors import DomainError
from inside_game.settings import Settings

MATCH_SETS = [
    "matches",
    "match_teams",
    "match_lineups",
    "lineup_positions",
    "lineup_cards",
    "events",
    "event_passes",
    "event_shots",
    "event_relations",
    "event_tactics",
    "tactical_lineups",
    "tracking_runs",
    "tracking_periods",
    "frames_360",
    "shot_freeze_players",
    "frame_360_players",
    "event_tracking_links",
]
TEMPLATES = frozenset(
    {
        "catalog",
        "match",
        "tracking",
        "movement",
        "occupancy",
        "event_match",
        "anchor_tracking",
    }
)
JSON_COLUMNS = frozenset(
    {
        "details",
        "height",
        "body_part",
        "pass_type",
        "outcome",
        "technique",
        "shot_type",
        "config",
        "visible_area",
    }
)


def normalize(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value).lower()
    if isinstance(value, (date, datetime, daytime)):
        return value.isoformat()
    return value


class CliTokenProvider:
    """Use the existing CLI login; tokens stay in memory and are never logged."""

    def __init__(self):
        self.lock = threading.Lock()
        self.token, self.expires = "", 0

    def get_token(self, *scopes, **kwargs):
        with self.lock:
            if self.expires > time.time() + 120:
                return SimpleNamespace(token=self.token, expires_on=self.expires)
            cli = os.getenv("AZURE_CLI_PATH") or shutil.which("az")
            if not cli:
                raise DomainError(
                    "DATABASE_UNAVAILABLE",
                    "Azure CLI login is required; run az login.",
                    503,
                )
            args = [
                "account",
                "get-access-token",
                "--resource",
                "https://database.windows.net/",
                "-o",
                "json",
            ]
            if os.name == "nt" and cli.lower().endswith(".cmd"):
                command = [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "& '" + cli.replace("'", "''") + "' " + " ".join(args),
                ]
            else:
                command = [cli, *args]
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=90,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode:
                raise DomainError(
                    "DATABASE_UNAVAILABLE",
                    "Azure authentication failed; renew the CLI login.",
                    503,
                )
            data = json.loads(result.stdout)
            self.token, self.expires = (
                data["accessToken"],
                int(data.get("expires_on", time.time() + 300)),
            )
            return SimpleNamespace(token=self.token, expires_on=self.expires)


class SqlRepository:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.cache, self.lock = {}, threading.RLock()
        self.provider = CliTokenProvider()
        if os.getenv("INSIDE_GAME_SQL_AUTH") == "managed_identity":
            from azure.identity import ManagedIdentityCredential

            self.provider = ManagedIdentityCredential(client_id=os.getenv("AZURE_CLIENT_ID"))

    def _connect(self):
        import mssql_python

        for value in (self.settings.server, self.settings.database):
            if not re.fullmatch(r"[a-zA-Z0-9_.-]+", value):
                raise DomainError(
                    "INVALID_CONFIGURATION", "Invalid SQL configuration.", 503
                )
        connection = mssql_python.connect(
            f"Server={self.settings.server};Database={self.settings.database};Encrypt=yes;TrustServerCertificate=no;",
            token_provider=self.provider,
            timeout=90,
            autocommit=True,
        )
        try:
            connection.timeout = 15
            cursor = connection.cursor()
            if self.settings.reader_user:
                # Server configuration only; never supplied by an API request.
                if self.settings.reader_user != "inside_game_api_reader":
                    raise DomainError(
                        "INVALID_CONFIGURATION", "Unregistered SQL context.", 503
                    )
                cursor.execute("EXECUTE AS USER='inside_game_api_reader';")
            cursor.execute(
                "SELECT IS_ROLEMEMBER('football_reader') AS reader, HAS_PERMS_BY_NAME(DB_NAME(),'DATABASE','CONTROL') AS admin, IS_ROLEMEMBER('db_datawriter') AS writer, IS_ROLEMEMBER('db_ddladmin') AS ddl_admin, HAS_PERMS_BY_NAME('statsbomb.matches','OBJECT','UPDATE') AS can_update;"
            )
            role = cursor.fetchone()
            if role[0] != 1 or any(v == 1 for v in role[1:]):
                raise DomainError(
                    "UNSAFE_DATABASE_IDENTITY",
                    "API database identity must be a limited analytics reader.",
                    503,
                )
            cursor.close()
            return connection
        except Exception:
            connection.close()
            raise

    def execute(self, template: str, parameters=()):
        if template not in TEMPLATES:
            raise DomainError("UNREGISTERED_QUERY", "Query is not registered.")
        statement = (
            files("inside_game")
            .joinpath("sql", template + ".sql")
            .read_text(encoding="utf-8")
        )
        connection = None
        try:
            connection = self._connect()
            cursor = connection.cursor()
            cursor.execute(statement, tuple(parameters))
            sets = []
            while True:
                if cursor.description:
                    names = [c[0] for c in cursor.description]
                    rows = []
                    for row in cursor.fetchall():
                        item = {k: normalize(v) for k, v in zip(names, row)}
                        for k in JSON_COLUMNS & item.keys():
                            if isinstance(item[k], str):
                                item[k] = json.loads(item[k])
                        rows.append(item)
                    sets.append(rows)
                if not cursor.nextset():
                    break
            cursor.close()
            return sets
        except DomainError:
            raise
        except Exception as exc:
            raise DomainError(
                "DATABASE_UNAVAILABLE",
                "Azure SQL is unavailable or the query timed out.",
                503,
            ) from exc
        finally:
            if connection:
                try:
                    if self.settings.reader_user:
                        cursor = connection.cursor()
                        cursor.execute("REVERT;")
                        cursor.close()
                finally:
                    connection.close()

    def _cached(self, key, build):
        with self.lock:
            cached = self.cache.get(key)
            if cached and cached[0] > time.monotonic():
                return cached[1]
            value = build()
            self.cache[key] = (time.monotonic() + self.settings.cache_seconds, value)
            return value

    def catalog(self):
        def build():
            matches, teams, players = self.execute("catalog")
            return {
                "matches": [
                    m for m in matches if m["match_id"] in self.settings.allowed_matches
                ],
                "teams": teams,
                "players": players,
            }

        return self._cached("catalog", build)

    def match(self, match_id: int):
        if match_id not in self.settings.allowed_matches:
            raise DomainError("MATCH_NOT_FOUND", "Match is not available.", 404)

        def build():
            sets = self.execute("match", [match_id])
            if not sets or not sets[0]:
                raise DomainError("MATCH_NOT_FOUND", "Published match not found.", 404)
            data = dict(zip(MATCH_SETS, sets))
            meta = next(
                (m for m in self.catalog()["matches"] if m["match_id"] == match_id),
                None,
            )
            if not meta:
                raise DomainError("MATCH_NOT_FOUND", "Match is not available.", 404)
            data["meta"] = meta
            digest = hashlib.sha256(
                json.dumps(data, sort_keys=True, default=str).encode()
            ).hexdigest()
            data["revision"] = digest
            data["event_index"] = {e["event_id"]: e for e in data["events"]}
            data["passes"] = {e["event_id"]: e for e in data["event_passes"]}
            data["shots"] = {e["event_id"]: e for e in data["event_shots"]}
            return data

        return self._cached(("match", match_id), build)

    def tracking(
        self, match_id, run_id, period, start, end, stride=1, team=None, player=None
    ):
        frames, players, balls = self.execute(
            "tracking", [match_id, run_id, period, start, end, stride, team, player]
        )
        by_frame = {
            f["frame_index"]: {**f, "players": [], "ball": None} for f in frames
        }
        for p in players:
            by_frame[p["frame_index"]]["players"].append(p)
        for b in balls:
            by_frame[b["frame_index"]]["ball"] = b
        return list(by_frame.values())

    def event_match(self, event_id):
        rows = self.execute(
            "event_match", [event_id, json.dumps(self.settings.allowed_matches)]
        )[0]
        if not rows:
            raise DomainError("EVENT_NOT_FOUND", "Event is not available.", 404)
        return self.match(rows[0]["match_id"])

    def anchor_tracking(self, run_id, event_ids):
        frames, players, balls = self.execute(
            "anchor_tracking", [run_id, json.dumps(event_ids)]
        )
        by_frame = {
            (f["period"], f["frame_index"]): {**f, "players": [], "ball": None}
            for f in frames
        }
        for p in players:
            by_frame[p["period"], p["frame_index"]]["players"].append(p)
        for b in balls:
            by_frame[b["period"], b["frame_index"]]["ball"] = b
        return list(by_frame.values())

    def movement(self, match_id, run_id, period, start, end, team=None, player=None):
        # One aggregate read per match/window serves all players and rankings.
        rows = self._cached(
            ("movement", match_id, run_id, period, start, end),
            lambda: self.execute(
                "movement", [match_id, run_id, period, start, end, None, None]
            )[0],
        )
        return [
            r
            for r in rows
            if (team is None or r["team_id"] == team)
            and (player is None or r["player_id"] == player)
        ]

    def occupancy(
        self, match_id, run_id, period, start, end, team, player, grid, orient, bounds
    ):
        return self.execute(
            "occupancy",
            [match_id, run_id, period, start, end, team, player, grid, orient, *bounds],
        )[0]
