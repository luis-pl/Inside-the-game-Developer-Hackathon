"""Construcción de la web del agente de insights, de la intención al lienzo.

Sin red ni LLM: el agente de datos es el fixture sintético de la galería. Cada
plantilla se pide por `/api/ask` como lo hace el navegador y se comprueba lo que
la persona recibiría: piezas completas, HTML bien formado, nada de valores
internos a la vista, texto escapado, informe independiente coherente, degradación
ante fallos de datos y respuestas concurrentes.
"""

import copy
import json
import re
import threading
import time
from contextlib import asynccontextmanager
from html.parser import HTMLParser

import pytest
from starlette.testclient import TestClient

from inside_game.agents.insights_agent.agent import InsightsAgent
from inside_game.agents.insights_agent.runtime import Runtime
from inside_game.agents.insights_agent.web import create_app
from inside_game.insights.demo import demo_manifest
from inside_game.tools.evidence_client import EvidenceClient

FIXTURE = {e["operation"]: e["response"] for e in demo_manifest()["evidence"]}
BASE = "http://127.0.0.1:8030"
BUDGET_S = 3  # la reconstrucción completa local; el objetivo de producto es 10 s
HOSTILE = '<img src=x onerror="alert(1)"><script>alert(2)</script>'

INTENTS = {
    "match_overview": {"template_id": "match_overview", "match_id": 900001},
    "player_dossier": {
        "template_id": "player_dossier",
        "match_id": 900001,
        "player_id": 103,
    },
    "entity_comparison": {"template_id": "entity_comparison", "match_id": 900001},
    "tactical_episode": {"template_id": "tactical_episode", "match_id": 900001},
    "custom_report": {
        "template_id": "custom_report",
        "match_id": 900001,
        "insight_ids": ["shot_map", "pass_map", "passing_network"],
    },
}


def match(home="Synthetic FC 1"):
    return {
        "match_id": 900001,
        "home_team_id": 1,
        "home_team_name": home,
        "away_team_id": 2,
        "away_team_name": "Synthetic FC 2",
        "is_synthetic": True,
        "provider": None,
    }


def context(home="Synthetic FC 1", player="Jugador 103"):
    return {
        "match": match(home),
        "lineups": [
            {"match_id": 900001, "team_id": 1, "player_id": i, "jersey_number": i % 100}
            | {"player_name": player if i == 103 else f"Jugador {i}"}
            for i in (101, 102, 103)
        ]
        + [
            {
                "match_id": 900001,
                "team_id": 2,
                "player_id": i,
                "jersey_number": i % 100,
                "player_name": f"Jugador {i}",
            }
            for i in (201, 202)
        ],
        "position_intervals": [],
        "periods": [
            {"period": 1, "home_attacks_positive_x": True, "duration_ms": 2700000},
            {"period": 2, "home_attacks_positive_x": False, "duration_ms": 2700000},
        ],
    }


class FakeApi:
    def __init__(self, ctx=None, down=(), overrides=None):
        self.ctx = ctx or context()
        self.down = set(down)
        self.overrides = overrides or {}

    async def call(self, operation, arguments):
        if operation == "list_matches":
            response = copy.deepcopy(FIXTURE["get_shots"])
            response["operation_id"] = "list_matches"
            response["data"] = {"items": [self.ctx["match"]]}
            return response, None
        if operation in self.down:
            return None, "API_UNAVAILABLE"
        if operation not in FIXTURE:
            return None, "SOURCE_FIELD_UNAVAILABLE"
        response = copy.deepcopy(self.overrides.get(operation, FIXTURE[operation]))
        if operation == "get_match_context":
            response["data"] = copy.deepcopy(self.ctx)
        return response, None


def web(api=None, profiles=None, **kwargs):
    api = api or FakeApi(**kwargs)

    @asynccontextmanager
    async def open_fake():
        def new_data():
            return EvidenceClient(api)

        yield Runtime(
            new_agent=lambda: InsightsAgent(new_data(), profiles=profiles or {}),
            new_data=new_data,
            model=None,
            data_source="API falsa",
        )

    return TestClient(create_app(open_fake, port=8030), base_url=BASE)


class Page(HTMLParser):
    """Estructura de un fragmento: etiquetas, atributos, texto visible, scripts."""

    VOID = frozenset(
        {"meta", "br", "hr", "img", "input", "link", "area", "base", "col"}
    )

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.stack, self.errors = [], []
        self.tags, self.attrs, self.scripts = [], [], []
        self.text, self.ids = [], []
        self._raw = None
        self._pre = 0  # JSON de evidencia en «Fuentes y alcance»: auditoría, no lectura
        self.feed(html)
        self.close()
        if self.stack:
            self.errors.append(f"sin cerrar: {self.stack[-3:]}")

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs += [(tag, k, v) for k, v in attrs]
        self.ids += [v for k, v in attrs if k == "id"]
        if tag in ("script", "style"):
            self._raw = (tag, dict(attrs).get("type"), [])
        if tag == "pre":
            self._pre += 1
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs += [(tag, k, v) for k, v in attrs]
        self.ids += [v for k, v in attrs if k == "id"]

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"</{tag}> inesperado; abierto: {self.stack[-3:]}")
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
            return
        self.stack.pop()
        if tag == "pre":
            self._pre -= 1
        if self._raw and self._raw[0] == tag:
            if tag == "script":
                self.scripts.append((self._raw[1], "".join(self._raw[2])))
            self._raw = None

    def handle_data(self, data):
        if self._raw:
            self._raw[2].append(data)
        elif not self._pre:
            self.text.append(data)

    @property
    def visible(self):
        return " ".join("".join(self.text).split())


def ask(client, intent):
    started = time.perf_counter()
    response = client.post("/api/ask", json={"intent": intent})
    return response, time.perf_counter() - started


@pytest.fixture(scope="module")
def built():
    """Cada plantilla construida una vez: respuesta, tiempo y estructura."""
    out = {}
    with web() as client:
        for name, intent in INTENTS.items():
            response, elapsed = ask(client, intent)
            data = response.json()
            out[name] = {
                "status": response.status_code,
                "elapsed": elapsed,
                "data": data,
                "canvas": Page(data.get("canvas_html", "")),
                "message": Page(data["message_html"]),
                "client_get": client.get,
            }
        yield out


@pytest.mark.parametrize("name", INTENTS)
def test_every_template_builds_a_canvas_inside_the_time_budget(built, name):
    result = built[name]
    assert result["status"] == 200
    assert result["elapsed"] < BUDGET_S
    assert "canvas_html" in result["data"], result["message"].visible
    assert result["data"]["report_url"].startswith("/reports/")


@pytest.mark.parametrize("name", INTENTS)
def test_canvas_and_message_are_well_formed_html(built, name):
    assert built[name]["canvas"].errors == []
    assert built[name]["message"].errors == []


@pytest.mark.parametrize("name", INTENTS)
def test_each_piece_has_title_question_status_and_unique_id(built, name):
    page = built[name]["canvas"]
    html = built[name]["data"]["canvas_html"]
    sections = re.findall(r'<section class="insight" id="([^"]+)"', html)
    assert sections, "el lienzo no tiene piezas"
    assert len(set(page.ids)) == len(page.ids), "ids repetidos en el lienzo"
    assert page.tags.count("h2") >= len(sections)
    assert html.count('class="block-question"') == len(sections)
    assert "Lectura calculada sobre la evidencia" not in html
    assert html.count('class="status') >= len(sections)


@pytest.mark.parametrize("name", INTENTS)
def test_payload_matches_the_pieces_shown(built, name):
    page = built[name]["canvas"]
    html = built[name]["data"]["canvas_html"]
    sections = re.findall(r'<section class="insight" id="([^"]+)"', html)
    payloads = [body for kind, body in page.scripts if kind == "application/json"]
    assert len(payloads) == 1
    payload = json.loads(payloads[0])
    assert [b["id"] for b in payload["blocks"]] == sections
    assert {b["state"] for b in payload["blocks"]} <= {"ready", "partial"}
    assert payload["teams"] and payload["evidence"]
    assert "</script" not in payloads[0].lower()


@pytest.mark.parametrize("name", INTENTS)
def test_no_internal_values_or_placeholders_reach_the_reader(built, name):
    for key in ("canvas", "message"):
        text = built[name][key].visible
        assert not re.search(r"\b(None|NaN|nan|undefined|null|Infinity)\b", text), text[
            :300
        ]
        assert not re.search(r"Unknown|\[object|\{\{|\}\}|Traceback", text)


@pytest.mark.parametrize("name", INTENTS)
def test_canvas_is_self_contained_and_runs_no_inline_code(built, name):
    page = built[name]["canvas"]
    assert [k for k, _ in page.scripts] == ["application/json"]
    assert not [a for a in page.attrs if a[1].startswith("on")]
    external = [
        a
        for a in page.attrs
        if a[1] in {"src", "href", "action"} and re.match(r"(https?:)?//", a[2] or "")
    ]
    assert external == []
    assert not {"iframe", "object", "embed", "link", "img"} & set(page.tags)


def test_message_reports_what_was_shown_and_what_was_not(built):
    overview = built["match_overview"]["message"].visible
    assert "SINTÉTICO" in overview or "sintéticos" in overview
    assert "Equipo protagonista por defecto" in overview
    assert built["match_overview"]["data"]["next"]["intent"]["match_id"] == 900001
    assert "Synthetic data" in built["match_overview"]["data"]["source_html"]


def test_standalone_report_has_the_same_pieces_and_is_sandboxed(built):
    data = built["match_overview"]["data"]
    in_canvas = re.findall(
        r'<section class="insight" id="([^"]+)"', data["canvas_html"]
    )
    standalone = built["match_overview"]["client_get"](data["report_url"])
    assert standalone.status_code == 200
    assert standalone.headers["content-security-policy"].startswith("sandbox")
    doc = Page(standalone.text)
    assert doc.errors == []
    assert standalone.text.lower().startswith("<!doctype html>")
    assert {"html", "head", "title", "body"} <= set(doc.tags)
    in_doc = re.findall(r'<section class="insight" id="([^"]+)"', standalone.text)
    assert in_doc == in_canvas
    assert len(standalone.content) < 16 * 1024 * 1024


def test_hostile_names_are_escaped_everywhere():
    with web(ctx=context(home=f"Local {HOSTILE}", player=HOSTILE)) as client:
        for name in ("match_overview", "player_dossier"):
            response, _ = ask(client, INTENTS[name])
            data = response.json()
            fragments = [
                data["message_html"],
                data.get("canvas_html", ""),
                data.get("source_html", ""),
                client.get(data["report_url"]).text,
            ]
            for html in fragments:
                page = Page(html)
                assert "<img" not in html and "<script>alert" not in html
                assert not [a for a in page.attrs if a[1].startswith("on")]
                assert "img" not in page.tags
            assert "&lt;img" in data["canvas_html"] or "&lt;img" in data["message_html"]


def test_follow_up_rebuilds_the_page_and_keeps_the_previous_report():
    with web() as client:
        first = client.post(
            "/api/ask", json={"intent": INTENTS["match_overview"]}
        ).json()
        follow = {**first["next"]["intent"], "period": 2}
        second = client.post("/api/ask", json={"intent": follow}).json()
        assert second["report_id"] != first["report_id"]
        assert second["canvas_html"] != first["canvas_html"]
        again = client.get(f"/api/reports/{first['report_id']}").json()
        assert again["canvas_html"] == first["canvas_html"]
        assert second["next"]["intent"]["period"] == 2


def test_failed_data_degrades_to_a_message_with_reasons_not_to_an_error_page():
    with web(down={"get_shots", "get_passes"}) as client:
        response, _ = ask(client, INTENTS["match_overview"])
        data = response.json()
        assert response.status_code == 200 and "canvas_html" in data
        page = Page(data["message_html"])
        assert page.errors == []
        assert "no disponibles" in page.visible
        assert "Shot map" in page.visible and "API_UNAVAILABLE" in page.visible
        assert "Shot map" not in re.findall(
            r"<h2>([^<]*)</h2>", data["canvas_html"]
        )


def test_nothing_to_show_returns_a_clear_message_without_a_canvas():
    everything = {op for op in FIXTURE if op != "get_match_context"}
    with web(down=everything) as client:
        response, _ = ask(client, INTENTS["match_overview"])
        data = response.json()
        assert response.status_code == 200 and "canvas_html" not in data
        text = Page(data["message_html"]).visible
        assert "No hay piezas que mostrar" in text
        assert "piezas no disponibles" in text
        assert data["next"]["intent"]["match_id"] == 900001


def test_unknown_match_or_player_is_a_message_not_a_server_error():
    with web() as client:
        for intent in (
            {"template_id": "match_overview", "match_id": 900001, "team_id": 99},
            {"template_id": "player_dossier", "match_id": 900001, "player_id": 999},
            {"template_id": "tactical_episode", "match_id": 900001, "time_ms": 5000},
        ):
            response = client.post("/api/ask", json={"intent": intent})
            assert response.status_code < 500
            data = response.json()
            assert "message_html" in data
            assert "canvas_html" not in data
            assert Page(data["message_html"]).errors == []


def test_simultaneous_requests_are_answered_or_refused_never_mixed():
    results = []
    with web() as client:

        def go(period):
            intent = {**INTENTS["match_overview"], "period": period}
            response = client.post("/api/ask", json={"intent": intent})
            results.append((response.status_code, response.json()))

        threads = [threading.Thread(target=go, args=(1 + i % 2,)) for i in range(4)]
        [t.start() for t in threads]
        [t.join() for t in threads]
    assert {status for status, _ in results} <= {200, 429}
    done = [data for status, data in results if status == 200]
    assert done, "al menos una petición se atiende"
    assert len({d["report_id"] for d in done}) == len(done)
    for status, data in results:
        if status == 429:
            assert "message_html" in data and "canvas_html" not in data


def test_every_recipe_has_its_own_question_instead_of_the_generic_subtitle():
    from inside_game.insights.catalog import RECIPES

    assert [k for k, r in RECIPES.items() if not r.get("question")] == []


def test_evidence_footer_groups_pages_by_query_and_keeps_every_anchor():
    from inside_game.insights.contracts import Evidence
    from inside_game.insights.organisms import evidence_footer

    base = next(
        e for e in demo_manifest()["evidence"] if e["operation"] == "get_events"
    )
    rows = []
    for page in (1, 2, 3):
        row = copy.deepcopy(base)
        row["evidence_id"] = f"q6-p{page}"
        rows.append(Evidence.model_validate(row))
    single = copy.deepcopy(base)
    single["evidence_id"] = "q2-p1"
    rows.append(Evidence.model_validate(single))

    html = evidence_footer(rows)
    page = Page(html)
    assert page.errors == []
    assert "2 queries (4 pages)" in page.visible
    assert "q6 · get_events · synthetic · 3 pages" in page.visible
    assert "q2 · get_events · synthetic" in page.visible
    # Todas las páginas siguen siendo destino de los enlaces «Evidencia» de las piezas.
    assert all(f'id="evidence-q6-p{n}"' in html for n in (1, 2, 3))
    assert 'id="evidence-q2-p1"' in html
    # Plegado: nada de lo anterior está abierto por defecto.
    assert " open" not in html


@pytest.mark.parametrize("name", INTENTS)
def test_reader_never_sees_raw_api_metric_keys(built, name):
    text = built[name]["canvas"].visible
    for raw in (
        "aggregate.",
        "summary.",
        "event_counts",
        "outcomes.",
        "body_parts",
        "tackles_won",
        "channel_",
        "channel 1",
        "time_ms",
        "event_id",
        "events_in_supplied",
    ):
        assert raw not in text, f"{raw!r} llega al lector"


def test_match_overview_shows_a_per_team_table_with_both_team_names(built):
    canvas = built["match_overview"]["canvas"]
    assert "By team" in canvas.visible
    assert "Synthetic FC 1" in canvas.visible and "Synthetic FC 2" in canvas.visible
    assert "table" in canvas.tags


def test_web_canvas_applies_the_source_profile_like_the_exported_report():
    actions = copy.deepcopy(FIXTURE["get_ball_actions"])
    actions["data"]["summary"] = {"dribble_attempts": 0, "carries": 4}
    profile = {
        "synthetic": {
            "measured_match_id": 900001,
            "unavailable": {},
            "zero_only": {},
            "unannotated_metrics": {"ball_progression": ["dribble_attempts"]},
        }
    }
    intent = {
        "template_id": "custom_report",
        "match_id": 900001,
        "insight_ids": ["ball_progression"],
    }
    with web(profiles=profile, overrides={"get_ball_actions": actions}) as client:
        data = client.post("/api/ask", json={"intent": intent}).json()
        standalone = client.get(data["report_url"]).text
    assert "Carries" in data["canvas_html"]
    assert "Attempted dribbles" not in data["canvas_html"]
    assert "Attempted dribbles" not in standalone
