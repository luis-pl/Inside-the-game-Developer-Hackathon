"""BFF del espacio de trabajo: cookies HttpOnly, claves sólo en memoria del servidor.

El acceso automático es una opción explícita para loopback. Para compartir el
servidor se desactiva y cada miembro entra con su propia credencial de equipo.
"""

import argparse
import asyncio
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.staticfiles import StaticFiles

from inside_game.agents_cli import app_from_env, load_local_env
from inside_game.tools.mcp_client import DataMcpSettings


def create_workspace(agent_app, *, frontend_dir, local_key=None):
    @asynccontextmanager
    async def lifespan(app):
        yield
        tasks = list(agent_app.state.chat.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )
    sessions = {}
    frontend_dir = Path(frontend_dir)

    @app.middleware("http")
    async def browser_guard(request, call_next):
        if request.url.path.startswith(("/workspace-api", "/dashboard-api")):
            # Cabecera no simple + mismo origen evitan solicitudes CSRF incluso en localhost.
            origin = request.headers.get("origin")
            if (origin and origin != str(request.base_url).rstrip("/")) or (
                request.method != "GET"
                and request.headers.get("x-inside-game") != "workspace"
            ):
                return JSONResponse(
                    {"error": {"code": "INVALID_ORIGIN"}}, status_code=403
                )
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse(
                    {"error": {"code": "INVALID_ORIGIN"}}, status_code=403
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith(("/workspace-api", "/dashboard-api")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/workspace-api/session")
    async def login(request: Request):
        for sid in list(sessions):
            if sessions[sid][1] <= time.monotonic():
                sessions.pop(sid)
        if len(sessions) >= 100:
            return JSONResponse(
                {"error": {"code": "SESSION_CAPACITY"}}, status_code=429
            )
        auth = request.headers.get("authorization", "")
        key = auth[7:] if auth.lower().startswith("bearer ") else ""
        if (
            not key
            and local_key
            and request.client
            and request.client.host in {"127.0.0.1", "::1", "testclient"}
        ):
            key = local_key
        # Verificación por el mismo middleware que protege las llamadas agénticas.
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=agent_app), base_url="http://127.0.0.1"
        ) as client:
            check = await client.get(
                "/a2a/v1/conversations", headers={"Authorization": "Bearer " + key}
            )
        if check.status_code != 200:
            return JSONResponse({"error": {"code": "UNAUTHORIZED"}}, status_code=401)
        sid = secrets.token_urlsafe(32)
        sessions[sid] = (key, time.monotonic() + 3600)
        response = JSONResponse({"authenticated": True})
        response.delete_cookie("inside_game_session", path="/workspace-api")
        response.set_cookie(
            "inside_game_session",
            sid,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            max_age=3600,
            path="/",
        )
        return response

    @app.delete("/workspace-api/session")
    async def logout(request: Request):
        sessions.pop(request.cookies.get("inside_game_session"), None)
        response = JSONResponse({"authenticated": False})
        response.delete_cookie("inside_game_session", path="/")
        response.delete_cookie("inside_game_session", path="/workspace-api")
        return response

    @app.get("/workspace-api/config")
    async def config():
        return {"local_demo": bool(local_key)}

    async def viewer_service(request):
        from inside_game.dashboard.config import DashboardConfig
        from inside_game.dashboard.gateway import EpisodeService, HttpOperations

        session = sessions.get(request.cookies.get("inside_game_session"))
        if not session or session[1] <= time.monotonic():
            return None
        url = DataMcpSettings.from_env().url.removesuffix("/mcp")
        return EpisodeService(HttpOperations(DashboardConfig(url, session[0])))

    @app.get("/dashboard-api/matches")
    async def viewer_matches(request: Request):
        from inside_game.dashboard.gateway import DataError

        service = await viewer_service(request)
        if not service:
            return JSONResponse(
                {"error": "Inicia sesión en el espacio de análisis."}, status_code=401
            )
        try:
            return await asyncio.to_thread(service.matches)
        except DataError as exc:
            return JSONResponse({"error": str(exc)}, status_code=exc.status)

    @app.get("/dashboard-api/episode")
    async def viewer_episode(
        request: Request,
        matchId: int,
        period: int,
        startSeconds: int,
        durationSeconds: int = 300,
    ):
        from inside_game.dashboard.gateway import DataError

        service = await viewer_service(request)
        if not service:
            return JSONResponse(
                {"error": "Inicia sesión en el espacio de análisis."}, status_code=401
            )
        try:
            return await asyncio.to_thread(
                service.episode,
                matchId,
                period,
                startSeconds,
                duration_seconds=durationSeconds,
            )
        except DataError as exc:
            return JSONResponse({"error": str(exc)}, status_code=exc.status)
        except ValueError:
            return JSONResponse({"error": "Ventana inválida."}, status_code=422)

    @app.api_route("/workspace-api/{path:path}", methods=["GET", "POST"])
    async def proxy(path: str, request: Request):
        import re

        # No proxy arbitrario de URLs o de otras rutas del servidor.
        if not re.fullmatch(
            r"(?:conversations(?:/[0-9a-f-]{36}(?:/(?:messages|page))?)?|chat-catalog)",
            path,
        ):
            return Response(status_code=404)
        session = sessions.get(request.cookies.get("inside_game_session"))
        if not session or session[1] <= time.monotonic():
            return JSONResponse({"error": {"code": "SESSION_EXPIRED"}}, status_code=401)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 24000:
                return Response(status_code=413)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=agent_app), base_url="http://127.0.0.1"
        ) as client:
            result = await client.request(
                request.method,
                "/a2a/v1/" + path,
                content=bytes(raw),
                headers={
                    "Authorization": "Bearer " + session[0],
                    "Content-Type": "application/json",
                },
            )
        return Response(
            result.content,
            status_code=result.status_code,
            media_type=result.headers.get("content-type", "application/json"),
        )

    if (frontend_dir / "assets").is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=frontend_dir / "assets"),
            name="workspace-assets",
        )

    @app.get("/")
    @app.get("/viewer")
    async def index():
        if not (frontend_dir / "index.html").is_file():
            return JSONResponse(
                {"error": {"code": "BUILD_FRONTEND_FIRST"}}, status_code=503
            )
        return FileResponse(
            frontend_dir / "index.html", headers={"Cache-Control": "no-cache"}
        )

    app.mount("/", agent_app)

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument(
        "--local-demo",
        action="store_true",
        help="Usa la credencial agent-data sólo en este equipo",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    load_local_env(root)
    app = create_workspace(
        app_from_env(args.port),
        frontend_dir=root / "frontend/dist",
        local_key=DataMcpSettings.from_env().key if args.local_demo else None,
    )
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
