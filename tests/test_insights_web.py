"""Página web del agente de insights, compuesta con el diseño atómico. Sin red ni LLM."""

import copy
import re
from contextlib import asynccontextmanager

from starlette.testclient import TestClient

from inside_game.agents.insights_agent.agent import InsightsAgent
from inside_game.agents.insights_agent.runtime import Runtime
from inside_game.agents.insights_agent.web import Reports, create_app
from inside_game.insights.demo import demo_manifest
from inside_game.tools.evidence_client import EvidenceClient

FIXTURE = {e["operation"]: e["response"] for e in demo_manifest()["evidence"]}
MATCH = {
    "match_id": 900001,
    "home_team_id": 1,
    "home_team_name": "Synthetic FC 1",
    "away_team_id": 2,
    "away_team_name": "Synthetic FC 2",
    "is_synthetic": True,
    "provider": None,
}
CONTEXT = {
    "match": MATCH,
    "lineups": [],
    "position_intervals": [],
    "periods": [{"period": 1, "home_attacks_positive_x": True, "duration_ms": 2700000}],
}
INTENT = {
    "template_id": "custom_report",
    "match_id": 900001,
    "insight_ids": ["shot_map"],
}
BASE = "http://127.0.0.1:8030"


class FakeApi:
    async def call(self, operation, arguments):
        if operation == "list_matches":
            response = copy.deepcopy(FIXTURE["get_shots"])
            response["operation_id"] = "list_matches"
            response["data"] = {"items": [MATCH]}
            return response, None
        response = copy.deepcopy(FIXTURE[operation])
        if operation == "get_match_context":
            response["data"] = copy.deepcopy(CONTEXT)
        return response, None


def runtime_factory():
    @asynccontextmanager
    async def open_fake():
        def new_data():
            return EvidenceClient(FakeApi())

        yield Runtime(
            new_agent=lambda: InsightsAgent(new_data(), profiles={}),
            new_data=new_data,
            model=None,
            data_source="API falsa",
        )

    return open_fake()


def client():
    return TestClient(create_app(runtime_factory, port=8030), base_url=BASE)


def test_page_is_the_atomic_workspace_without_inline_scripts():
    with client() as c:
        page = c.get("/")
        assert page.status_code == 200 and 'class="workspace"' in page.text
        assert '<script src="/assets/insights.js"' in page.text
        # Ningún script ejecutable en línea; sólo archivos del mismo origen.
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", page.text)
        csp = page.headers["content-security-policy"]
        assert (
            "script-src 'self'" in csp
            and "'unsafe-inline'" not in csp.split("style-src-attr")[0]
        )
        # Organismos del formulario: partidos agrupados por fuente y sin IDs a la vista.
        assert 'label="Demostración · datos sintéticos"' in page.text
        assert ">Synthetic FC 1 vs Synthetic FC 2</option>" in page.text
        # Sin modelo, se abre «Elegir informe» y la pregunta escrita queda deshabilitada.
        assert (
            'id="tab-pick" aria-controls="panel-pick" aria-selected="true"' in page.text
        )


def test_assets_bundle_the_report_design_system_and_the_workspace():
    with client() as c:
        css = c.get("/assets/insights.css")
        js = c.get("/assets/insights.js")
        assert (
            css.headers["content-type"].startswith("text/css")
            and ".insight{" in css.text
        )
        assert ".masthead{" in css.text
        assert "function initInsightsReport(root,payload)" in js.text
        assert 'classList.contains("workspace")' in js.text


def test_ask_returns_fragments_built_from_the_same_organisms():
    with client() as c:
        data = c.post("/api/ask", json={"intent": INTENT}).json()
        assert 'class="msg answer"' in data["message_html"]
        assert "Synthetic data" in data["source_html"]
        # El lienzo usa los organismos del informe exportado y sus datos.
        assert '<section class="insight"' in data["canvas_html"]
        assert 'class="report-payload"' in data["canvas_html"]
        assert data["next"]["intent"]["match_id"] == 900001
        restored = c.get(f"/api/reports/{data['report_id']}").json()
        assert restored["canvas_html"] == data["canvas_html"]
        standalone = c.get(data["report_url"])
        assert standalone.status_code == 200 and "<!doctype html>" in standalone.text
        assert standalone.headers["content-security-policy"].startswith("sandbox")
        assert c.get("/api/reports/" + "0" * 32).status_code == 404


def test_questions_without_a_model_come_back_as_an_error_message():
    with client() as c:
        data = c.post("/api/ask", json={"question": "Resumen del 900001"}).json()
        assert 'class="msg error"' in data["message_html"]
        assert "MODEL_UNAVAILABLE" in data["message_html"]
        assert "canvas_html" not in data


def test_other_sites_cannot_use_the_local_api():
    with client() as c:
        # Rebinding de DNS: Host distinto de loopback.
        assert c.get("/", headers={"host": "evil.example"}).status_code == 403
        # Otra web intentando gastar tokens desde el navegador del usuario.
        foreign = c.post(
            "/api/ask",
            json={"intent": INTENT},
            headers={"origin": "https://evil.example"},
        )
        assert foreign.status_code == 403
        plain = c.post("/api/ask", content="{}", headers={"content-type": "text/plain"})
        assert plain.status_code == 415
        big = c.post(
            "/api/ask",
            content="x" * 70000,
            headers={"content-type": "application/json"},
        )
        assert big.status_code == 413 and "message_html" in big.json()


def test_only_the_latest_reports_are_kept():
    reports = Reports(limit=2)
    first = reports.add("a")
    reports.add("b")
    reports.add("c")
    assert first not in reports.items and len(reports.items) == 2
