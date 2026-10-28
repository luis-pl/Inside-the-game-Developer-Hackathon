"""API de OpenCode Console/Zen o Go; facturación separada de Azure.

El destino está fijado al endpoint oficial del plan seleccionado. Nunca se
reutilizan credenciales Azure/MCP ni se cambia de Console a Go implícitamente.
Este cliente no compra crédito, no cambia planes y no hace fallback de proveedor.
"""

import asyncio
import json
import os
import sqlite3
import time
from contextlib import closing
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from inside_game.providers.models import (
    AzureChatModel,
    AzureResponsesModel,
    ModelFailure,
)

CONSOLE_ENDPOINT = "https://opencode.ai/inference/openai/v1"
GO_ENDPOINT = "https://opencode.ai/inference/go/openai/v1"
ENDPOINTS = {"opencode": CONSOLE_ENDPOINT, "opencode-go": GO_ENDPOINT}
FREE_GO_MODELS = {"beam-free", "longcat-2.5-preview-free"}
_go_session = ContextVar("inside_game_go_session", default=None)


@dataclass(frozen=True)
class OpenCodeModelSettings:
    endpoint: str = CONSOLE_ENDPOINT
    deployment: str = "gpt-6-luna"
    api_key: str = field(default="", repr=False)
    api: str = "responses"
    reasoning_effort: str = "medium"
    max_output_tokens: int = 4096
    timeout_seconds: float = 60
    provider: str = "opencode"
    auth_mode: str = "api_key"
    cli_db: str = ""
    free_only: bool = False

    def __post_init__(self):
        if self.provider not in ENDPOINTS or self.endpoint != ENDPOINTS[self.provider]:
            raise ValueError("Use the official OpenCode endpoint for the selected plan")
        if self.auth_mode not in {"api_key", "cli_session"}:
            raise ValueError("Unsupported OpenCode authentication mode")
        if self.auth_mode == "cli_session" and (
            self.provider != "opencode-go" or self.api_key or not self.cli_db
        ):
            raise ValueError(
                "CLI session authentication requires explicit Go and its local database"
            )
        if self.auth_mode == "api_key" and (
            not isinstance(self.api_key, str)
            or not self.api_key
            or self.api_key.strip() != self.api_key
        ):
            raise ValueError(
                "OpenCode API key for the selected plan is missing or invalid"
            )
        if (
            not isinstance(self.deployment, str)
            or not self.deployment
            or self.deployment.endswith("-free")
            and not (
                self.provider == "opencode-go" and self.deployment in FREE_GO_MODELS
            )
            or self.deployment == "big-pickle"
        ):
            raise ValueError("Select a Console model available to external API clients")
        if self.free_only and (
            self.auth_mode != "cli_session" or self.deployment not in FREE_GO_MODELS
        ):
            raise ValueError(
                "Free-only mode requires a verified free Go model and CLI session"
            )
        if self.api not in {"responses", "chat_completions"}:
            raise ValueError("Unsupported OpenCode model API")
        if self.reasoning_effort not in {"none", "low", "medium", "high"}:
            raise ValueError("Unsupported reasoning effort")
        if not 256 <= self.max_output_tokens <= 8192:
            raise ValueError("Invalid model output budget")
        if not 0 < self.timeout_seconds <= 120:
            raise ValueError("Invalid model timeout")

    @classmethod
    def from_env(cls, provider="opencode"):
        if provider not in ENDPOINTS:
            raise ValueError("Unsupported OpenCode plan")
        auth_mode = os.getenv("INSIDE_GAME_OPENCODE_AUTH_MODE", "api_key")
        key = (
            os.getenv("INSIDE_GAME_OPENCODE_API_KEY", "")
            if auth_mode == "api_key"
            else ""
        )
        if not key and auth_mode == "api_key":
            # /connect de OpenCode guarda el JSON fuera del repositorio. No se
            # acepta opencode-go como sustituto silencioso de Console/Zen.
            path = Path(
                os.getenv(
                    "INSIDE_GAME_OPENCODE_AUTH_FILE",
                    str(Path.home() / ".local/share/opencode/auth.json"),
                )
            )
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
                entry = document.get(provider, {})
                if entry.get("type") == "api":
                    key = entry.get("key", "")
            except (OSError, ValueError, AttributeError):
                raise ValueError(
                    "OpenCode credentials for selected plan unavailable"
                ) from None
        return cls(
            endpoint=ENDPOINTS[provider],
            provider=provider,
            deployment=os.getenv("INSIDE_GAME_OPENCODE_MODEL", "gpt-6-luna"),
            api_key=key,
            api=os.getenv("INSIDE_GAME_OPENCODE_API", "responses"),
            reasoning_effort=os.getenv("INSIDE_GAME_REASONING_EFFORT", "medium"),
            auth_mode=auth_mode,
            cli_db=os.getenv(
                "INSIDE_GAME_OPENCODE_CLI_DB",
                str(Path.home() / ".local/share/opencode/opencode.db"),
            ),
            free_only=os.getenv("INSIDE_GAME_OPENCODE_FREE_ONLY", "0") == "1",
        )


def read_cli_session(path):
    """Read only the active account; never copy or refresh credentials ourselves."""
    try:
        with closing(
            sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
        ) as db:
            row = db.execute(
                "SELECT a.url,a.access_token,a.token_expiry,s.active_org_id "
                "FROM account a JOIN account_state s ON s.active_account_id=a.id "
                "WHERE s.id=1"
            ).fetchone()
        if row is None:
            raise ValueError
        server, token, expiry, org = row
        if server not in {"https://console.opencode.ai", "https://opencode.ai/console"}:
            raise ValueError
        if (
            not token
            or any(c in token for c in "\r\n")
            or not org
            or not org.replace("_", "").isalnum()
        ):
            raise ValueError
        if not isinstance(expiry, (int, float)) or expiry <= time.time() * 1000 + 30000:
            raise ModelFailure("MODEL_CLI_SESSION_EXPIRED")
        return server, token, org
    except (OSError, sqlite3.Error, TypeError, ValueError):
        raise ModelFailure("MODEL_AUTHENTICATION_FAILED") from None


class _ConsoleAuthorization:
    async def _post(self, path, body):
        if self.settings.provider != "opencode-go":
            return await super()._post(path, body)
        # ContextVar mantiene la sesión UUID entre turnos y reintentos sin
        # mezclar consumidores que comparten la misma instancia del proveedor.
        session = None
        for message in body.get("input", body.get("messages", [])):
            if message.get("role") == "user":
                try:
                    session = str(UUID(json.loads(message["content"])["request_id"]))
                except (ValueError, KeyError, TypeError):
                    raise ModelFailure("MODEL_SESSION_REQUIRED") from None
                break
        if session is None:
            raise ModelFailure("MODEL_SESSION_REQUIRED")
        token = _go_session.set(session)
        try:
            return await super()._post(path, body)
        finally:
            _go_session.reset(token)

    async def _headers(self):
        # Identidad propia: no se finge ser el cliente OpenCode ni se envían
        # cabeceras de Azure. Las redirecciones permanecen deshabilitadas.
        headers = {
            "Authorization": "Bearer " + self.settings.api_key,
            "User-Agent": "inside-game-sports-data-agent/0.0.0",
        }
        if self.settings.auth_mode == "cli_session":
            server, token, org = await asyncio.to_thread(
                read_cli_session, self.settings.cli_db
            )
            headers.update(Authorization="Bearer " + token)
            headers["x-opencode-org-id"] = org
            if self.settings.free_only:
                response = await self._http.get(
                    server + "/api/config",
                    headers={
                        "Authorization": headers["Authorization"],
                        "x-org-id": org,
                        "User-Agent": headers["User-Agent"],
                    },
                )
                if response.status_code != 200:
                    raise ModelFailure("MODEL_FREE_STATUS_UNVERIFIED")
                try:
                    provider = response.json()["config"]["provider"]["opencode-go"]
                    model_info = provider["models"][self.settings.deployment]
                    cost = model_info["cost"]
                    if (
                        provider["api"] != GO_ENDPOINT
                        or not all(
                            type(cost.get(k)) in (int, float) and cost[k] == 0
                            for k in ("input", "output")
                        )
                        or any(
                            cost.get(k, 0) != 0 for k in ("cache_read", "cache_write")
                        )
                    ):
                        raise ValueError
                    limits = model_info.get("limit")
                    native = limits.get("context") if isinstance(limits, dict) else None
                    self.context_window_tokens = (
                        native if type(native) is int and native > 0 else None
                    )
                except (ValueError, TypeError, KeyError):
                    raise ModelFailure("MODEL_FREE_STATUS_UNVERIFIED") from None
        if self.settings.provider == "opencode-go":
            session = _go_session.get()
            if session is None:
                raise ModelFailure("MODEL_SESSION_REQUIRED")
            headers["x-opencode-session"] = session
        return headers


class OpenCodeResponsesModel(_ConsoleAuthorization, AzureResponsesModel):
    """Reutiliza Responses y la preservación de llamadas/razonamiento del agente."""


class OpenCodeChatModel(_ConsoleAuthorization, AzureChatModel):
    """Chat Completions con el mismo ejecutor y validación MCP."""
