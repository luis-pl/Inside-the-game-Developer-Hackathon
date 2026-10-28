import asyncio
import json
import time
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from test_interpreter_workspace import Planner
from test_sports_analyst import KEY, records

from inside_game.access import KeyRegistry
from inside_game.agents.analyst_contracts import AnalysisSection, Statement
from inside_game.agents.conversation_copy import (
    catalog_reply,
    concept_reply,
    report_reply,
)
from inside_game.agents.http_api import create_agent_app
from inside_game.insights.analysis_note import analyst_copy


def test_catalog_preserves_orientation_and_omits_internal_identifiers():
    result = catalog_reply(
        "Podemos mirar ocasiones y pases.",
        [{"match_id": 900001, "home_team_name": "Azul", "away_team_name": "Rojo"}],
    )
    assert result.startswith("Podemos mirar ocasiones y pases.")
    assert "Azul — Rojo" in result and "900001" not in result
    assert "Match selector" in result


def test_definitions_do_not_promise_missing_xg_or_geometric_control():
    reply = concept_reply("xg", "Cualquier partido", [{"provider": "Metrica Sports"}])
    assert "has no available xG" in reply and "Cualquier" not in reply
    assert "illustrative" in concept_reply("xg", "")
    assert "does not establish" in concept_reply("voronoi", "")
    assert "Select a match" not in concept_reply(
        "welcome", "", [{"match_id": 900001}]
    )
    assert concept_reply("general", "Otra explicación") == "Otra explicación"


def test_chat_uses_grounded_sports_statements_and_keeps_scope_visible():
    analysis = SimpleNamespace(
        status="partial",
        sections=[
            AnalysisSection(
                heading="Contexto",
                statements=[
                    Statement(
                        kind="observation",
                        text="El partido consultado.",
                        fact_ids=["source"],
                    )
                ],
            ),
            AnalysisSection(
                heading="Lo más importante",
                statements=[
                    Statement(
                        kind="observation",
                        text="Azul terminó con 14 tiros frente a los 9 de Rojo.",
                        fact_ids=["source"],
                    )
                ],
            ),
        ],
        facts=[SimpleNamespace(provenance={"is_synthetic": True})],
    )
    reply = report_reply(analysis, partial=True)
    assert "14 tiros" in reply and "synthetic" in reply and "limited scope" in reply
    assert "El partido consultado" not in reply and "Creé" not in reply
    assert "retains its data" in report_reply(None, reused=True)
    analysis.status = "error"
    assert "14 tiros" not in report_reply(analysis, partial=True)


def test_report_reader_preserves_sources_and_escapes_untrusted_copy():
    result = analyst_copy(
        "Análisis\nProcedencia: datos sintéticos.\n\nOcasiones\nLectura <script>danger()</script> [1].\nAlcance y límites\nUna muestra, no todo el partido.\nOtra limitación.\nReferencias\n[1] fuente: <unsafe>"
    )
    assert "<script>" not in result and "&lt;script&gt;" in result
    assert "Una muestra, no todo el partido." in result.split("<details")[0]
    assert "<summary>Sources and references</summary>" in result
    assert "[1] fuente: &lt;unsafe&gt;" in result and "Otra limitación." in result
    assert "open=" not in result


@pytest.mark.parametrize(
    "action,stage",
    [("answer", "complete"), ("catalog", "complete"), ("clarify", "clarification")],
)
def test_conversational_turns_do_not_create_reports(action, stage):
    async def run():
        model = Planner(action=action)
        app = create_agent_app(credentials=records(), model_factory=lambda: model)
        for _, _, principal in KeyRegistry(records()).entries:
            app.state.chat.catalogs[principal.id] = (
                time.monotonic() + 300,
                [
                    {
                        "match_id": 900011,
                        "home_team_name": "Azul",
                        "away_team_name": "Rojo",
                    }
                ],
            )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": "Bearer " + KEY},
        ) as client:
            cid = (await client.post("/a2a/v1/conversations")).json()["id"]
            await client.post(
                f"/a2a/v1/conversations/{cid}/messages",
                json={
                    "request_id": str(uuid4()),
                    "text": "Ayúdame a entender el fútbol",
                },
            )
            await asyncio.gather(*app.state.chat.tasks)
            value = (await client.get(f"/a2a/v1/conversations/{cid}")).json()
            assert value["stage"] == stage and value["report"] is None
            assert not app.state.store.pages
            assert "error" not in value["runs"][-1]
            if action == "catalog":
                assert "Azul — Rojo" in value["messages"][-1]["content"]
                assert "900011" not in value["messages"][-1]["content"]
            assert KEY not in json.dumps(value)

    asyncio.run(run())
