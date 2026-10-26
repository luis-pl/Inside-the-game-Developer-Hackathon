"""Página local del agente de insights, construida con el diseño atómico.

    python -m inside_game.agents.insights_agent.web --port 8030 --data-agent-url http://127.0.0.1:8010
    python -m inside_game.agents.insights_agent.web --azure-model gpt-5-mini-1

La página es una instancia del template «espacio de trabajo» de la librería de
insights (átomos → moléculas → organismos → template → página). En cada petición
el servidor compone con las mismas piezas la respuesta de la conversación y el
lienzo del informe (`report_parts`); el JS del navegador sólo los coloca.

Sólo escucha en loopback. El modelo se usa únicamente si se elige en el comando
(`--azure-model`) o en el entorno; sin modelo, «Elegir informe» no consume
tokens. La conversación (`next`) vive en el navegador; el servidor guarda sólo
los últimos informes para «Abrir en otra pestaña» y para recargar la página.
"""

import argparse
import asyncio
import json
import os
from collections import OrderedDict
from contextlib import asynccontextmanager
from uuid import uuid4

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route

from inside_game.insights.catalog import RECIPES
from inside_game.insights.molecules import (
    answer_card,
    clarification_card,
    notice_card,
    source_tag,
)
from inside_game.insights.organisms import report_canvas
from inside_game.insights.pages import render_report, render_workspace, report_parts
from inside_game.insights.templates import CSS, JS, WORKSPACE_CSS, WORKSPACE_JS

from .merge import merge_manifests
from .profiles import source_key
from .runtime import load_settings, open_runtime

MAX_BODY = 64 * 1024
MAX_REPORTS = 12
KEEP_MANIFESTS = 3
SUGGESTIONS = (
    "¿Desde dónde remató el Equipo B en Metrica 2?",
    "Compara a los dos equipos del partido SC 03",
    "¿Qué hizo el dorsal 10 del SC 01 · Equipo A?",
)
# Sin scripts en línea; los organismos usan atributos `style` para colores de equipo.
PAGE_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; "
    "style-src-attr 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)
# Informe exportado abierto en otra pestaña: su propia CSP y aislado del origen.
REPORT_CSP = "sandbox allow-scripts allow-downloads allow-modals"
HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}
SOURCE_GROUPS = (
    ("Datos reales · Metrica Sports", lambda m: source_key(m) == "Metrica Sports"),
    ("Datos reales · SkillCorner", lambda m: source_key(m) == "SkillCorner"),
    ("Demostración · datos sintéticos", lambda m: bool(m.get("is_synthetic"))),
)


class Reports:
    """Últimos informes en memoria; un proceso largo no acumula megabytes."""

    def __init__(self, limit=MAX_REPORTS):
        self.limit = limit
        self.items = OrderedDict()

    def add(self, item):
        report_id = uuid4().hex
        self.items[report_id] = item
        while len(self.items) > self.limit:
            self.items.popitem(last=False)
        # La evidencia (manifiesto) sólo sirve para ampliar el informe actual: los
        # antiguos conservan su HTML pero no los megabytes de datos.
        for old in list(self.items.values())[:-KEEP_MANIFESTS]:
            if isinstance(old, dict):
                old.pop("manifest", None)
        return report_id


def match_groups(rows):
    """Partidos agrupados por fuente para el formulario; sin IDs a la vista."""
    groups, placed = [], set()
    for label, belongs in SOURCE_GROUPS:
        matches = [
            (
                r["match_id"],
                f"{r['home_team_name']} vs {r['away_team_name']}",
                [
                    {"team_id": r["home_team_id"], "name": r["home_team_name"]},
                    {"team_id": r["away_team_id"], "name": r["away_team_name"]},
                ],
            )
            for r in rows
            if belongs(r) and r["match_id"] not in placed
        ]
        placed.update(m[0] for m in matches)
        if matches:
            groups.append((label, matches))
    return groups


def message_for(answer, extra=()):
    """La respuesta del agente como molécula de la conversación."""
    if answer.kind == "report":
        labels = answer.labels
        return answer_card(
            answer.title or "Informe",
            source_tag(labels.synthetic, labels.provider) if labels else "",
            [b.title for b in answer.blocks],
            [*answer.notes, *extra],
            [(RECIPES[d.insight_id]["title"], d.reason) for d in answer.discarded],
            has_report=answer.has_report,
        )
    if answer.kind == "clarification" and answer.clarification:
        return clarification_card(
            answer.clarification.question, answer.clarification.options
        )
    if answer.kind == "declined":
        return notice_card("declined", answer.summary)
    return notice_card("error", answer.summary, answer.issues)


def create_app(runtime_factory, *, port):
    """`runtime_factory` es un context manager asíncrono que produce un Runtime."""
    state = {"runtime": None, "catalog": None}
    reports = Reports()
    # Una petición al modelo/datos a la vez: evita ráfagas de tokens y de API.
    busy = asyncio.Semaphore(1)
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    @asynccontextmanager
    async def lifespan(app):
        async with runtime_factory() as runtime:
            state["runtime"] = runtime
            yield

    def guard(request, *, json_body=False):
        """Sólo loopback y mismo origen; protege la API local (y los tokens) de otras webs."""
        if request.headers.get("host") not in allowed_hosts:
            return JSONResponse({"error": "HOST_NOT_ALLOWED"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin not in {f"http://{h}" for h in allowed_hosts}:
            return JSONResponse({"error": "ORIGIN_NOT_ALLOWED"}, status_code=403)
        if json_body and request.headers.get("content-type", "").split(";")[0] != (
            "application/json"
        ):
            return JSONResponse({"error": "JSON_REQUIRED"}, status_code=415)
        return None

    def refused(code, message, status):
        return JSONResponse(
            {"error": code, "message_html": notice_card("error", message, [code])},
            status_code=status,
        )

    async def catalog():
        """Partidos del agente de datos; se conservan tras la primera lectura correcta."""
        if state["catalog"] is None:
            pages, error = (
                await state["runtime"].new_data().fetch("list_matches", {"limit": 100})
            )
            if error:
                return []
            state["catalog"] = match_groups(
                [r for p in pages for r in p["response"]["data"]["items"]]
            )
        return state["catalog"]

    async def page(request):
        if denied := guard(request):
            return denied
        runtime = state["runtime"]
        details = (
            f"Las preguntas escritas las interpreta {runtime.model}. Datos: {runtime.data_source}."
            if runtime.model
            else f"Sin modelo para preguntas escritas. Datos: {runtime.data_source}."
        )
        html = render_workspace(
            await catalog(),
            [(k, r["title"]) for k, r in RECIPES.items()],
            bool(runtime.model),
            details,
            SUGGESTIONS,
        )
        return HTMLResponse(
            html, headers={**HEADERS, "Content-Security-Policy": PAGE_CSP}
        )

    def asset(content, media_type):
        async def serve(request):
            if denied := guard(request):
                return denied
            return Response(content, media_type=media_type, headers=HEADERS)

        return serve

    async def ask(request):
        if denied := guard(request, json_body=True):
            return denied
        body = await request.body()
        if len(body) > MAX_BODY:
            return refused("BODY_TOO_LARGE", "La petición es demasiado grande.", 413)
        try:
            payload = json.loads(body)
        except ValueError:
            return refused("INVALID_JSON", "La petición no es válida.", 400)
        if busy.locked():
            return refused(
                "BUSY", "Ya hay un informe en preparación. Espera a que termine.", 429
            )
        # El informe al que se suma la petición no es parte del AskRequest del agente.
        append_to = (
            payload.pop("append_to", None) if isinstance(payload, dict) else None
        )
        async with busy:
            # El agente valida el AskRequest y responde con códigos, nunca excepciones.
            result = await state["runtime"].new_agent().ask(payload)
        answer = result.answer
        manifest, html = result.report_manifest, result.report_html
        title, turns, extra, merged = answer.title or "Informe", 1, (), False
        base = reports.items.get(append_to) if isinstance(append_to, str) else None
        if manifest and base and base.get("manifest"):
            # Misma conversación sobre el mismo partido: se acumula, no se reemplaza.
            joined = merge_manifests(base["manifest"], manifest, base["turns"] + 1)
            if joined:
                manifest, added = joined
                merged, turns, title = True, base["turns"], base["title"]
                html = base["html"]
                if added:
                    turns += 1
                    match = answer.labels.match if answer.labels else None
                    title = (
                        f"{match} · {len(manifest['blocks'])} piezas"
                        if match
                        else base["title"]
                    )
                    manifest["title"] = title
                    html = render_report(manifest)["html"]
                    count = len(manifest["blocks"])
                    extra = (
                        f"Se añadió al informe de la conversación: ahora tiene {count} piezas.",
                    )
                else:
                    extra = ("Esa pieza ya estaba en el informe; no se repitió.",)
        response = {
            "next": json.loads(answer.next.model_dump_json()) if answer.next else None,
            "message_html": message_for(answer, extra),
        }
        if manifest:
            # El lienzo se compone con las mismas piezas que el informe exportado.
            item = {
                "canvas_html": report_canvas(report_parts(manifest)),
                "title": title,
                "source_html": source_tag(
                    answer.labels.synthetic, answer.labels.provider
                )
                if answer.labels
                else "",
                "html": html,
                "manifest": manifest,
                "turns": turns,
            }
            report_id = reports.add(item)
            response |= {
                key: item[key] for key in ("canvas_html", "title", "source_html")
            } | {
                "report_id": report_id,
                "report_url": f"/reports/{report_id}",
                "merged": merged,
            }
        return JSONResponse(response)

    async def canvas(request):
        """Recupera el lienzo de un informe reciente (recargar la página)."""
        if denied := guard(request):
            return denied
        report_id = request.path_params["report_id"]
        item = reports.items.get(report_id)
        if item is None:
            return JSONResponse({"error": "REPORT_EXPIRED"}, status_code=404)
        return JSONResponse(
            {key: item[key] for key in ("canvas_html", "title", "source_html")}
            | {"report_id": report_id, "report_url": f"/reports/{report_id}"}
        )

    async def report(request):
        """Informe exportado autocontenido, para abrirlo en otra pestaña."""
        if denied := guard(request):
            return denied
        item = reports.items.get(request.path_params["report_id"])
        if item is None or not item["html"]:
            return JSONResponse({"error": "REPORT_EXPIRED"}, status_code=404)
        return Response(
            item["html"],
            media_type="text/html",
            headers={**HEADERS, "Content-Security-Policy": REPORT_CSP},
        )

    routes = [
        Route("/", page),
        Route("/assets/insights.css", asset(CSS + WORKSPACE_CSS, "text/css")),
        Route("/assets/insights.js", asset(JS + WORKSPACE_JS, "text/javascript")),
        Route("/api/ask", ask, methods=["POST"]),
        Route("/api/reports/{report_id:str}", canvas),
        Route("/reports/{report_id:str}", report),
    ]
    app = Starlette(routes=routes, lifespan=lifespan)
    app.state.reports = reports
    return app


def main():
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8030)
    parser.add_argument("--data-agent-url", help="URL A2A del agente de datos")
    parser.add_argument(
        "--azure-model",
        help="Despliegue Azure a usar para preguntas en texto (p. ej. gpt-5-mini-1)",
    )
    parser.add_argument(
        "--model-api", choices=["responses", "chat_completions"], default="responses"
    )
    args = parser.parse_args()
    load_settings()
    if args.azure_model:
        # Elección explícita en el comando; el endpoint y la clave vienen de .env.local.
        os.environ.update(
            INSIDE_GAME_MODEL_PROVIDER="azure",
            AZURE_OPENAI_DEPLOYMENT=args.azure_model,
            INSIDE_GAME_MODEL_AUTH="api_key",
            INSIDE_GAME_MODEL_API=args.model_api,
        )
        # Interpretar una pregunta no necesita razonamiento largo: con «low» el
        # planificador acierta lo mismo (16/16) en la mitad de tiempo y tokens.
        os.environ.setdefault("INSIDE_GAME_REASONING_EFFORT", "low")

    def runtime_factory():
        return open_runtime(data_agent_url=args.data_agent_url)

    app = create_app(runtime_factory, port=args.port)
    print(f"Agente de insights (web): http://127.0.0.1:{args.port}/", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
