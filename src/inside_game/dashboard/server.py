"""Loopback-only UI server. API secrets stay on the server and URLs are fixed."""

import argparse
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .config import DashboardConfig
from .gateway import DataError, EpisodeService, HttpOperations


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, service_factory, **kwargs):
        self.service_factory = service_factory
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        # No query strings, upstream responses or credentials in access logs.
        pass

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
        )
        super().end_headers()

    def respond(self, status, data):
        body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        host = self.headers.get("Host", "").split(":")[0]
        if host not in ("localhost", "127.0.0.1"):
            return self.respond(403, {"error": "Acceso local únicamente."})
        origin = self.headers.get("Origin")
        if origin and origin not in (
            f"http://{self.headers.get('Host')}",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ):
            return self.respond(403, {"error": "Origen no permitido."})
        url = urlsplit(self.path)
        if not url.path.startswith("/dashboard-api/"):
            if url.path in ("/", "/index.html"):
                # El servidor clásico sigue abriendo el visor; el CLI workspace
                # sirve el mismo bundle con el chat como entrada principal.
                body = (Path(self.directory) / "index.html").read_bytes().replace(
                    b"<head>", b'<head><meta name="inside-game-surface" content="viewer">', 1
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            return super().do_GET()
        if not self.server.slots.acquire(blocking=False):
            return self.respond(
                429, {"error": "Consulta en curso; espera y reintenta."}
            )
        try:
            service = self.service_factory()
            if url.path == "/dashboard-api/matches":
                return self.respond(200, service.matches())
            if url.path == "/dashboard-api/episode":
                params = parse_qs(url.query, strict_parsing=True)
                required = {"matchId", "period", "startSeconds"}
                allowed = required | {"durationSeconds"}
                if (
                    not required.issubset(params)
                    or set(params) - allowed
                    or any(len(v) != 1 for v in params.values())
                ):
                    raise ValueError()
                return self.respond(
                    200,
                    service.episode(
                        *[
                            int(params[k][0])
                            for k in ("matchId", "period", "startSeconds")
                        ],
                        duration_seconds=int(params.get("durationSeconds", ["2700"])[0]),
                    ),
                )
            return self.respond(404, {"error": "Ruta no encontrada."})
        except DataError as error:
            return self.respond(error.status, {"error": str(error)})
        except ValueError:
            return self.respond(
                400,
                {
                    "error": "Configuración o parámetros inválidos. Revisa .env y la ventana."
                },
            )
        except (KeyError, TypeError):
            return self.respond(
                502,
                {
                    "error": "La respuesta de datos no coincide con el contrato esperado."
                },
            )
        finally:
            self.server.slots.release()


def main():
    parser = argparse.ArgumentParser(
        description="Inside the Game · Topology Lab (local)"
    )
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    directory = root / "frontend" / "dist"
    if not (directory / "index.html").exists():
        parser.error("Compila primero el frontend: cd frontend; npm ci; npm run build")

    def factory():
        return EpisodeService(HttpOperations(DashboardConfig.load(root)))

    handler = partial(
        DashboardHandler, directory=str(directory), service_factory=factory
    )
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    server.slots = threading.BoundedSemaphore(2)
    print(f"Topology Lab: http://127.0.0.1:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
