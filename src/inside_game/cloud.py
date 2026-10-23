"""Contenedor Azure: API + MCP con la misma identidad de credencial validada.

Cada petición MCP autentica la clave externa y la propaga por un transporte
ASGI interno hacia la API. Así no se pierde al titular detrás de una clave de
servicio compartida. No existe bypass local en este proceso de nube.
"""

import json
import logging
import os
import re
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware import Middleware
from starlette.responses import JSONResponse

from inside_game.access import mcp_credential, mcp_principal
from inside_game.api import create_app
from inside_game.mcp_server import MAX_REQUEST, McpSettings, create_server
from inside_game.settings import Settings

log = logging.getLogger("inside_game.audit")


class CloudMcpAccess:
    """Exige una clave vigente en todo /mcp, incluido descubrimiento de tools."""

    def __init__(self, app, registry):
        self.app, self.registry = app, registry

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        authorization = headers.get(b"authorization", b"").decode("latin-1")
        key = authorization[7:] if authorization.lower().startswith("bearer ") else ""
        principal = self.registry.verify(key)
        if principal is None:
            log.warning(
                json.dumps(
                    {
                        "event": "mcp_auth_rejected",
                        "request_id": str(uuid4()),
                        "status_code": 401,
                    }
                )
            )
            return await JSONResponse(
                {
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "A valid individual bearer credential is required.",
                    }
                },
                status_code=401,
                headers={
                    "WWW-Authenticate": 'Bearer realm="inside-game"',
                    "Cache-Control": "no-store",
                },
            )(scope, receive, send)
        # El middleware externo de la API también registra el transporte /mcp.
        # Comparte la identidad validada para no etiquetar una llamada MCP
        # autorizada como anónima en ese registro de acceso.
        state = scope.setdefault("state", {})
        state["credential_id"] = principal.id
        state["credential_role"] = principal.role
        token = mcp_credential.set(key)
        identity = mcp_principal.set(principal)
        try:
            await self.app(scope, receive, send)
        finally:
            mcp_principal.reset(identity)
            mcp_credential.reset(token)


def create_cloud_app(settings=None, repository=None, public_host=None):
    """Construye el servicio público y falla si no se configuraron identidades."""
    settings = settings or Settings.from_env()
    host = public_host or os.getenv("INSIDE_GAME_PUBLIC_HOST", "")
    if settings.local_access or settings.api_key or not settings.credentials:
        raise ValueError(
            "Cloud requires individual credentials, LOCAL_ACCESS=false and no shared API key"
        )
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.-]*", host):
        raise ValueError("Cloud requires an explicit public hostname")
    api = create_app(settings, repository)

    def audit(name, failed):
        principal = mcp_principal.get()
        log.warning(
            json.dumps(
                {
                    "event": "mcp_tool",
                    "request_id": str(uuid4()),
                    "credential_id": principal.id if principal else "unauthenticated",
                    "role": principal.role if principal else None,
                    "operation": name,
                    "failed": bool(failed),
                }
            )
        )

    server = create_server(
        McpSettings(),
        httpx.ASGITransport(app=api),
        token_provider=mcp_credential.get,
        operation_provider=lambda: (
            mcp_principal.get().operations if mcp_principal.get() else ()
        ),
        audit_callback=audit,
    )
    mcp = server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        max_request_body_size=MAX_REQUEST,
        transport_security=TransportSecuritySettings(
            allowed_hosts=[host, host + ":*"],
            allowed_origins=["https://" + host],
        ),
    )
    mcp.user_middleware.insert(
        0, Middleware(CloudMcpAccess, registry=api.state.registry)
    )

    @asynccontextmanager
    async def lifespan(app):
        async with mcp.router.lifespan_context(mcp):
            yield

    api.router.lifespan_context = lifespan
    # Las rutas API se resuelven primero; el SDK gestiona /mcp sin modificarlo.
    api.mount("/", mcp)
    return api


app = create_cloud_app() if os.getenv("INSIDE_GAME_CLOUD") == "true" else None
