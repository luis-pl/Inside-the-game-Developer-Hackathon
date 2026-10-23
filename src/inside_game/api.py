"""HTTP access to registered analytics operations. No arbitrary query endpoint."""

import asyncio
import hashlib
import json
import logging
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, Path, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import Field

from inside_game import contracts as c
from inside_game.access import KeyRegistry
from inside_game.errors import DomainError
from inside_game.service import OPERATIONS, SPATIAL_OPERATIONS, AnalyticsService
from inside_game.settings import Settings
from inside_game.tools.synthetic_db import SqlRepository

log = logging.getLogger("inside_game.api")
bearer = HTTPBearer(auto_error=False)


class MatchQuery(c.ClosedModel):
    team_id: int | None = Field(None, gt=0)
    opponent_id: int | None = Field(None, gt=0)
    from_date: str | None = None
    to_date: str | None = None
    side: Literal["all", "home", "away"] = "all"
    limit: int = Field(100, ge=1, le=200)
    cursor: str | None = Field(None, max_length=1024)


class ActionQuery(c.ClosedModel):
    team_id: int | None = Field(None, gt=0)
    player_id: int | None = Field(None, gt=0)
    period: int | None = Field(None, ge=1, le=2)
    start_ms: int | None = Field(None, ge=0)
    end_ms: int | None = Field(None, gt=0)
    limit: int = Field(100, ge=1, le=200)
    cursor: str | None = Field(None, max_length=1024)
    view: Literal["events", "summary", "map", "timeline"] = "events"
    outcome: Literal["all", "on_target", "goal", "saved", "blocked", "off_target"] = (
        "all"
    )
    body_part: Literal["all", "head", "left_foot", "right_foot"] = "all"


def create_app(settings=None, repository=None):
    settings = settings or Settings.from_env()
    if settings.api_key and len(settings.api_key) < 32:
        raise ValueError("INSIDE_GAME_API_KEY must contain at least 32 characters")
    registry = KeyRegistry(settings.credentials)
    if not settings.local_access and not settings.api_key and not registry.entries:
        raise ValueError("Remote API access requires INSIDE_GAME_API_KEY")
    service = AnalyticsService(repository or SqlRepository(settings))
    app = FastAPI(
        title="Inside the game — Football Analytics API",
        version="1.0.0",
        description="25 consultas predeterminadas y 9 análisis espaciales sobre datos sintéticos de Azure SQL. Los POST de consulta son de sólo lectura.",
    )
    app.state.service, app.state.settings = service, settings
    app.state.registry = registry
    rates, lock = defaultdict(deque), threading.Lock()
    slots = threading.BoundedSemaphore(settings.max_concurrent)

    def authenticated(
        request: Request,
        credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ):
        host = request.client.host if request.client else ""
        local_host = request.url.hostname in ("127.0.0.1", "localhost", "::1")
        local = settings.local_access and host in ("127.0.0.1", "::1") and local_host
        valid_key = bool(
            settings.api_key
            and credential
            and secrets.compare_digest(credential.credentials, settings.api_key)
        )
        principal = registry.verify(credential.credentials) if credential else None
        if not local and not valid_key and principal is None:
            raise DomainError(
                "UNAUTHORIZED", "A valid bearer API key is required.", 401
            )
        identity = (
            principal.id
            if principal
            else (
                hashlib.sha256(credential.credentials.encode()).hexdigest()
                if valid_key
                else "local"
            )
        )
        request.state.principal = principal
        request.state.credential_id = identity
        request.state.credential_role = (
            principal.role if principal else "local" if local else "legacy"
        )
        operation = request.url.path.removeprefix("/api/operations/")
        if (
            principal
            and request.url.path.startswith("/api/operations/")
            and operation in OPERATIONS
            and operation not in principal.operations
        ):
            raise DomainError(
                "FORBIDDEN", "This credential cannot use the requested operation.", 403
            )
        with lock:
            now = time.monotonic()
            entries = rates[identity]
            while entries and entries[0] < now - 60:
                entries.popleft()
            if len(entries) >= settings.rate_per_minute:
                raise DomainError(
                    "RATE_LIMITED",
                    "Request limit reached. Retry after one minute.",
                    429,
                )
            entries.append(now)

    def sync_execute(operation, body, request_id):
        if not slots.acquire(blocking=False):
            raise DomainError(
                "BUSY", "Concurrent request limit reached. Retry shortly.", 429
            )
        try:
            return service.execute(operation, body, request_id)
        finally:
            slots.release()

    async def call(operation, body, request):
        principal = getattr(request.state, "principal", None)
        if principal and operation not in principal.operations:
            raise DomainError(
                "FORBIDDEN", "This credential cannot use the requested operation.", 403
            )
        request.state.operation = operation
        request.state.match_ids = getattr(
            body, "match_ids", [body.match_id] if hasattr(body, "match_id") else []
        )
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    sync_execute, operation, body, request.state.request_id
                ),
                timeout=30,
            )
        except TimeoutError as exc:
            raise DomainError(
                "TIME_BUDGET_EXCEEDED",
                "Request exceeded its time budget. Retry or select a smaller scope.",
                503,
            ) from exc
        encoded = jsonable_encoder(result)
        if (
            len(json.dumps(encoded, separators=(",", ":"), allow_nan=False).encode())
            > 1024 * 1024
        ):
            raise DomainError(
                "RESPONSE_TOO_LARGE", "Select a smaller window or page size.", 413
            )
        return result

    @app.middleware("http")
    async def request_context(request, call_next):
        started = time.monotonic()
        request.state.request_id = str(uuid4())
        if len(list(request.query_params.multi_items())) != len(request.query_params):
            return JSONResponse(
                {
                    "error": {
                        "code": "INVALID_ARGUMENT",
                        "message": "Repeated query parameters are not accepted.",
                    }
                },
                status_code=422,
            )
        length = request.headers.get("content-length", "0")
        try:
            oversized = int(length) > 65536
        except ValueError:
            oversized = True
        if oversized:
            return JSONResponse(
                {
                    "error": {
                        "code": "REQUEST_TOO_LARGE",
                        "message": "Request body is limited to 64 KiB.",
                    }
                },
                status_code=413,
            )
        if request.method == "POST":
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 65536:
                    return JSONResponse(
                        {
                            "error": {
                                "code": "REQUEST_TOO_LARGE",
                                "message": "Request body is limited to 64 KiB.",
                            }
                        },
                        status_code=413,
                    )
                chunks.append(chunk)
            request._body = b"".join(chunks)
        if (
            request.method == "POST"
            and request.url.path.startswith("/api/operations/")
            and request.query_params
        ):
            return JSONResponse(
                {
                    "error": {
                        "code": "INVALID_ARGUMENT",
                        "message": "Use the typed JSON body; query parameters are not accepted.",
                    }
                },
                status_code=422,
            )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        # Lista cerrada de campos: nunca registrar Authorization, claves o cuerpos.
        if settings.credentials:
            log.warning(
                json.dumps(
                    {
                        "event": "analytics_request",
                        "request_id": request.state.request_id,
                        "credential_id": getattr(
                            request.state, "credential_id", "unauthenticated"
                        ),
                        "role": getattr(request.state, "credential_role", None),
                        "operation": getattr(request.state, "operation", None),
                        "match_ids": getattr(request.state, "match_ids", []),
                        "status_code": response.status_code,
                        "duration_ms": round((time.monotonic() - started) * 1000),
                    }
                )
            )
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        headers = (
            {"WWW-Authenticate": "Bearer"}
            if exc.status == 401
            else {"Retry-After": "60"}
            if exc.status == 429
            else {}
        )
        return JSONResponse(
            {
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "request_id": request.state.request_id,
                }
            },
            status_code=exc.status,
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Do not echo arbitrary inputs (which may contain credentials or SQL).
        return JSONResponse(
            {
                "error": {
                    "code": "INVALID_ARGUMENT",
                    "message": "Request does not satisfy the operation contract.",
                    "fields": [
                        {"location": list(e["loc"]), "type": e["type"]}
                        for e in exc.errors()
                    ],
                    "request_id": request.state.request_id,
                }
            },
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        log.error(
            "request_failed id=%s type=%s", request.state.request_id, type(exc).__name__
        )
        return JSONResponse(
            {
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Request could not be completed.",
                    "request_id": request.state.request_id,
                }
            },
            status_code=500,
        )

    @app.get("/health", tags=["Service"])
    async def health():
        return {"status": "ok", "service": "inside-game-api", "database_checked": False}

    @app.get("/api/whoami", tags=["Service"], dependencies=[Depends(authenticated)])
    async def whoami(request: Request):
        """Comprueba qué identidad y permisos tiene la credencial presentada."""
        principal = getattr(request.state, "principal", None)
        return {
            "credential_id": request.state.credential_id,
            "role": request.state.credential_role,
            "expires_at": principal.expires_at if principal else None,
            "operations": sorted(principal.operations if principal else OPERATIONS),
        }

    @app.get("/api/operations", tags=["Catalog"], dependencies=[Depends(authenticated)])
    async def operations():
        return {
            "operations": [
                {
                    "name": name,
                    "path": "/api/operations/" + name,
                    "method": "POST",
                    "read_only": True,
                    "input_schema": model.model_json_schema(),
                    "output_schema": c.ApiResponse.model_json_schema(),
                }
                for name, model in OPERATIONS.items()
            ]
        }

    def register(operation, model):
        async def endpoint(body, request: Request):
            return await call(operation, body, request)

        endpoint.__annotations__["body"] = model
        endpoint.__name__ = operation
        app.add_api_route(
            "/api/operations/" + operation,
            endpoint,
            methods=["POST"],
            operation_id=operation,
            response_model=c.ApiResponse,
            dependencies=[Depends(authenticated)],
            tags=["Spatial" if operation in SPATIAL_OPERATIONS else "Queries"],
        )

    for name, model in OPERATIONS.items():
        register(name, model)

    @app.get(
        "/api/dataset",
        response_model=c.ApiResponse,
        tags=["Convenience"],
        dependencies=[Depends(authenticated)],
    )
    async def dataset(request: Request):
        return await call("describe_dataset", c.Empty(), request)

    @app.get(
        "/api/matches",
        response_model=c.ApiResponse,
        tags=["Convenience"],
        dependencies=[Depends(authenticated)],
    )
    async def matches(request: Request, query: Annotated[MatchQuery, Query()]):
        try:
            body = c.MatchList.model_validate(query.model_dump())
        except ValueError as exc:
            raise DomainError("INVALID_ARGUMENT", "Invalid match query.") from exc
        return await call("list_matches", body, request)

    @app.get(
        "/api/matches/{match_id}",
        response_model=c.ApiResponse,
        tags=["Convenience"],
        dependencies=[Depends(authenticated)],
    )
    async def match_context(request: Request, match_id: Annotated[int, Path(gt=0)]):
        if request.query_params:
            raise DomainError(
                "INVALID_ARGUMENT", "This endpoint does not accept query parameters."
            )
        return await call(
            "get_match_context", c.MatchRequest(match_id=match_id), request
        )

    @app.get(
        "/api/matches/{match_id}/shots",
        response_model=c.ApiResponse,
        tags=["Convenience"],
        dependencies=[Depends(authenticated)],
    )
    async def shots(
        request: Request,
        match_id: Annotated[int, Path(gt=0)],
        query: Annotated[ActionQuery, Query()],
    ):
        args = query.model_dump()
        period, start, end = (
            args.pop("period"),
            args.pop("start_ms"),
            args.pop("end_ms"),
        )
        if start is not None or end is not None:
            if period is None or start is None or end is None:
                raise DomainError(
                    "INVALID_ARGUMENT", "Window requires period, start_ms and end_ms."
                )
            scope = {
                "kind": "window",
                "period": period,
                "start_ms": start,
                "end_ms": end,
            }
        else:
            scope = (
                {"kind": "period", "period": period} if period else {"kind": "match"}
            )
        try:
            body = c.ShotsRequest(match_id=match_id, scope=scope, **args)
        except ValueError as exc:
            raise DomainError("INVALID_ARGUMENT", "Invalid shot query.") from exc
        return await call("get_shots", body, request)

    return app


app = create_app()
