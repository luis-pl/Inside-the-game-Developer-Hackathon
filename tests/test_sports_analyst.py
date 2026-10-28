"""Texto fundamentado, comunicación HTTP y preservación de gráficos reales MCP."""

import asyncio
import hashlib
import json
import time
from uuid import uuid4

import httpx
import pytest

from inside_game.agents.analyst_contracts import AnalysisRequest, Statement
from inside_game.agents.analyst_facts import (
    evidence_facts,
    render_statement,
    visual_facts,
)
from inside_game.agents.contracts import DataResult
from inside_game.agents.http_api import create_agent_app
from inside_game.agents.insights_http_client import PayloadParser
from inside_game.agents.sports_analyst import (
    AnalystLimits,
    SportsAnalyst,
    normalize_finish_arguments,
)
from inside_game.insights.demo import demo_manifest
from inside_game.providers.models import ModelTurn

KEY = "analyst-test-key-private-1234567890123456"
OTHER = "another-analyst-test-key-1234567890123456"


def evidence_result(request_id=None):
    selected = [
        e
        for e in demo_manifest()["evidence"]
        if e["operation"]
        in {"get_team_shape", "get_tracking_frame", "get_match_context"}
    ]
    return DataResult(
        request_id=request_id or uuid4(),
        status="complete",
        model="fixture",
        evidence=selected,
    )


def call(name, args):
    return ModelTurn(
        [
            {
                "type": "function_call",
                "call_id": str(uuid4()),
                "name": name,
                "arguments": json.dumps(args),
            }
        ]
    )


class RouterModel:
    name = "scripted-test-model"
    turns = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def respond(self, instructions, messages, tools):
        self.turns += 1
        root = json.loads(messages[0]["content"])
        if any(t["name"] == "finish_analysis" for t in tools):
            if not root["facts"] and len(messages) == 1:
                return call(
                    "request_data",
                    {
                        "request_text": "Recupera forma del equipo y frame del instante solicitado."
                    },
                )
            outputs = [
                json.loads(m["output"])
                for m in messages
                if m.get("type") == "function_call_output"
            ]
            reviewed = any(m.get("name") == "request_insights" for m in messages)
            if not reviewed:
                return call(
                    "request_insights",
                    {
                        "request_text": "Crea team_shape del equipo analizado con el frame suministrado."
                    },
                )
            facts = next(o["facts"] for o in reversed(outputs) if "facts" in o)
            chosen = next(
                f
                for f in facts
                if f.get("block_id") == "shape" and f["label"] == "width_m"
            )
            return call(
                "finish_analysis",
                {
                    "status": "complete",
                    "title": "Organización espacial",
                    "sections": [
                        {
                            "heading": "Forma del equipo",
                            "statements": [
                                {
                                    "kind": "observation",
                                    "text": "La anchura medida en este instante es {{"
                                    + chosen["id"]
                                    + "}} m.",
                                    "fact_ids": [chosen["id"]],
                                },
                                {
                                    "kind": "interpretation",
                                    "text": "Esta muestra permite describir la ocupación transversal; por sí sola no determina eficacia defensiva.",
                                    "fact_ids": [chosen["id"]],
                                },
                            ],
                        }
                    ],
                    "limitations": [
                        "Una observación no demuestra un patrón de todo el partido."
                    ],
                },
            )
        catalog = root["evidence_catalog"]
        ids = [
            e["evidence_id"]
            for e in catalog
            if e["operation"] in {"get_team_shape", "get_tracking_frame"}
        ]
        return call(
            "render_report",
            {
                "title": "Forma del equipo",
                "blocks": [
                    {
                        "id": "shape",
                        "insight_id": "team_shape",
                        "evidence_ids": ids,
                        "parameters": {"team_id": 1, "period": 1, "time_ms": 10000},
                    }
                ],
            },
        )


class Loopback(httpx.AsyncBaseTransport):
    app = None

    async def handle_async_request(self, request):
        return await httpx.ASGITransport(app=self.app).handle_async_request(request)


def records():
    return [
        {
            "id": str(i),
            "name": "test",
            "role": "agent",
            "expires_at": int(time.time()) + 3600,
            "sha256": hashlib.sha256(key.encode()).hexdigest(),
        }
        for i, key in enumerate([KEY, OTHER])
    ]


def test_http_analysis_data_insights_mcp_and_immutable_attachment(monkeypatch):
    async def run():
        model = RouterModel()
        transport = Loopback()
        calls = []

        async def data_runner(request, key, timeout):
            calls.append((request.context.match_ids, key))
            return evidence_result(request.request_id)

        app = create_agent_app(
            credentials=records(),
            model_factory=lambda: model,
            data_runner=data_runner,
            data_transport=transport,
            insights_transport=transport,
        )
        transport.app = app
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1:8085",
            headers={"Authorization": "Bearer " + KEY},
        ) as client:
            message = {
                "request_id": str(uuid4()),
                "request_text": "Analiza la forma del equipo en el instante suministrado y acompáñala con su gráfico.",
                "context": {"match_ids": [900001]},
            }
            response = await client.post("/a2a/v1/analysis-reports", json=message)
            assert response.status_code == 200, response.text
            result = response.json()
            analysis = result["analysis"]
            report = result["report"]
            assert analysis["status"] == "complete" and "anchura" in analysis["text"]
            assert analysis["facts"][0]["block_id"] == "shape"
            assert analysis["tool_trace"][-1]["status"] == "ok"
            assert calls == [([900001], KEY)]
            assert report["revision"] == 2
            before = await client.get(analysis["visual_report"]["artifact_url"])
            after = await client.get(report["artifact_url"])
            parsed = []
            for html in (before.text, after.text):
                p = PayloadParser()
                p.feed(html)
                parsed.append(json.loads("".join(p.parts)))
            assert parsed[0]["blocks"] == parsed[1]["blocks"]
            assert parsed[1]["analyst"]["text"] == analysis["text"]
            assert KEY not in after.text
            other = await client.get(
                report["artifact_url"], headers={"Authorization": "Bearer " + OTHER}
            )
            assert other.status_code == 404
            count = model.turns
            again = await client.post("/a2a/v1/analysis-reports", json=message)
            assert again.json() == result and model.turns == count
            stale = await client.post(
                f"/a2a/v1/reports/{report['report_id']}/analysis",
                json={"expected_revision": 1, "analyst": {"text": "Un cambio"}},
            )
            assert stale.status_code == 409
            from inside_game.agents.insights_http_client import HttpInsightsAgent
            from inside_game.providers.models import ModelFailure

            async def cannot_publish(*args, **kwargs):
                raise ModelFailure("INSIGHTS_BUSY")

            monkeypatch.setattr(HttpInsightsAgent, "attach", cannot_publish)
            failure = await client.post(
                "/a2a/v1/analysis-reports",
                json={
                    "request_text": "Analiza la forma con esta evidencia",
                    "data_result": evidence_result().model_dump(mode="json"),
                },
            )
            failed = failure.json()
            assert (
                failed["analysis"]["status"] == "partial" and failed["analysis"]["text"]
            )
            assert (
                failed["analysis"]["issues"] == ["INSIGHTS_BUSY"]
                and failed["report"]["report_id"]
                == failed["analysis"]["visual_report"]["report_id"]
            )

            original_run = SportsAnalyst.run

            async def expires_after_graph(self, message):
                completed = await original_run(self, message)
                return completed.model_copy(
                    update={
                        "status": "error",
                        "text": "",
                        "issues": ["DEADLINE_EXCEEDED"],
                    }
                )

            monkeypatch.setattr(SportsAnalyst, "run", expires_after_graph)
            late = (
                await client.post(
                    "/a2a/v1/analysis-reports",
                    json={
                        "request_text": "Analiza la forma",
                        "data_result": evidence_result().model_dump(mode="json"),
                    },
                )
            ).json()
            assert (
                late["report"]["report_id"]
                == late["analysis"]["visual_report"]["report_id"]
            )
            assert (
                late["analysis"]["status"] == "partial" and not late["analysis"]["text"]
            )
            assert late["analysis"]["issues"] == ["DEADLINE_EXCEEDED"]

    asyncio.run(run())


@pytest.mark.parametrize(
    "text,ids,code",
    [
        ("Se anotaron 99 goles.", None, "USE_FACT_PLACEHOLDERS_FOR_NUMBERS"),
        ("Se observó {{f-000000000000}}.", None, "PLACEHOLDER_REQUIRES_CITATION"),
        ("Una observación.", ["f-000000000000"], "UNKNOWN_FACT_REFERENCE"),
    ],
)
def test_fabricated_values_and_citations_are_rejected(text, ids, code):
    fact = evidence_facts(evidence_result().evidence)[0]
    with pytest.raises(ValueError, match=code):
        render_statement(
            Statement(kind="observation", text=text, fact_ids=ids or [fact.id]), [fact]
        )


def test_visual_metrics_cannot_import_new_untrusted_evidence():
    result = evidence_result()
    payload = {
        "evidence": [e.model_dump(mode="json") for e in result.evidence],
        "blocks": [],
    }
    payload["evidence"][0]["response"]["data"]["tampered"] = 99
    with pytest.raises(ValueError, match="UNTRUSTED_VISUAL_EVIDENCE"):
        visual_facts(payload, result.evidence)


def test_missing_match_clarification_and_deadline():
    class Clarifier:
        name = "test"

        async def respond(self, *_):
            return call(
                "finish_analysis",
                {
                    "status": "needs_clarification",
                    "clarification": "¿Qué partido quieres analizar?",
                },
            )

    result = asyncio.run(
        SportsAnalyst(Clarifier()).run({"request_text": "Analiza Liverpool"})
    )
    assert result.status == "needs_clarification" and not result.text

    class Slow:
        name = "test"

        async def respond(self, *_):
            await asyncio.sleep(1)

    result = asyncio.run(
        SportsAnalyst(Slow(), limits=AnalystLimits(timeout_seconds=0.02)).run(
            {"request_text": "Analiza"}
        )
    )
    assert result.issues == ["DEADLINE_EXCEEDED"]


def test_wrong_match_evidence_is_rejected_before_inference():
    data = evidence_result()
    data.evidence[0].arguments["match_id"] = 900002
    result = asyncio.run(
        SportsAnalyst(RouterModel()).run(
            AnalysisRequest(
                request_text="Analiza",
                context={"match_ids": [900001]},
                data_result=data,
            )
        )
    )
    assert result.status == "error" and result.issues == ["EVIDENCE_MATCH_MISMATCH"]


def test_public_analyst_contract_rejects_tool_urls_and_auth_required():
    async def run():
        app = create_agent_app(credentials=records())
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            assert (
                await client.post("/a2a/v1/analysis", json={"request_text": "Analiza"})
            ).status_code == 401
            response = await client.post(
                "/a2a/v1/analysis",
                json={"request_text": "Analiza", "url": "http://untrusted"},
                headers={"Authorization": "Bearer " + KEY},
            )
            assert response.status_code == 422 and "untrusted" not in response.text

    asyncio.run(run())


def test_double_encoded_finish_fields_are_decoded_without_coercing_numbers():
    args, fields = normalize_finish_arguments(
        json.dumps(
            {
                "status": '"complete", ',
                "sections": '[{"heading":"Forma","statements":[]}], ',
                "limitations": '["Sólo un instante"]',
                "title": '"Análisis"',
            }
        )
    )
    assert args["status"] == "complete" and isinstance(args["sections"], list)
    assert fields == ["status", "sections", "limitations", "title"]
    args, fields = normalize_finish_arguments(
        json.dumps({"status": '"complete" arbitrary-code', "sections": "[truncated"})
    )
    assert not fields and isinstance(args["sections"], str)


def test_missing_values_never_become_zero_facts():
    result = evidence_result()
    ev = result.evidence[0]
    ev.response.data = {"summary": {"shots": 12, "xg": None, "goals": 0}}
    facts = evidence_facts([ev])
    assert not any(f.label == "xg" for f in facts)
    assert next(f for f in facts if f.label == "goals").value == 0


def test_geometry_cannot_assign_a_tactical_phase():
    f = next(
        f
        for f in evidence_facts(evidence_result().evidence)
        if f.operation == "get_team_shape"
    )
    with pytest.raises(ValueError, match="UNSUPPORTED_TACTICAL_PHASE_FROM_GEOMETRY"):
        render_statement(
            Statement(
                kind="interpretation",
                text="Es compatible con una fase de transición.",
                fact_ids=[f.id],
            ),
            [f],
        )


def test_match_discovery_exposes_names_and_ids_as_sourced_facts():
    ev = evidence_result().evidence[0].model_copy(deep=True)
    ev.operation = "list_matches"
    ev.response.operation_id = "list_matches"
    ev.response.data = {
        "items": [
            {
                "match_id": 900001,
                "home_team_name": "Alias local",
                "away_team_name": "Alias visitante",
            }
        ]
    }
    facts = evidence_facts([ev])
    assert {f.value for f in facts} == {900001, "Alias local", "Alias visitante"}
    assert all(f.scope["match_id"] == 900001 for f in facts)


def test_topology_detail_tables_are_facts_and_method_notes_are_not_claims():
    ev = evidence_result().evidence[0].model_copy(deep=True)
    ev.operation = "get_persistent_structure"
    ev.response.data = {
        "samples": [
            {
                "period": 1,
                "time_ms": 10000,
                "result": {
                    "method": "rips",
                    "interpretation": "Not a tactical gap",
                    "betti": [{"epsilon_m": 15, "h0": 3, "h1": 1}],
                    "intervals": [
                        {
                            "dimension": 1,
                            "birth_m": 10.0,
                            "death_m": None,
                            "censored_at_40m": True,
                        }
                    ],
                },
            }
        ]
    }
    facts = evidence_facts([ev])
    labels = {f.label for f in facts}
    assert {"h0", "h1", "epsilon_m", "birth_m"} <= labels
    assert not {"method", "interpretation", "death_m"} & labels
    assert next(f for f in facts if f.label == "h1").scope["epsilon_m"] == 15


def test_table_only_visuals_provide_sourced_comparison_facts():
    from inside_game.insights.pages import report_parts

    manifest = demo_manifest()
    manifest["blocks"] = [
        b for b in manifest["blocks"] if b["insight_id"] == "entity_comparison"
    ]
    parts = report_parts(manifest)
    evidence = DataResult(
        request_id=uuid4(),
        status="complete",
        model="test",
        evidence=manifest["evidence"],
    ).evidence
    facts = visual_facts(parts["payload"], evidence)
    assert facts
    assert any("/rows/" in f.path for f in facts)
    assert all(f.evidence_ids for f in facts)
