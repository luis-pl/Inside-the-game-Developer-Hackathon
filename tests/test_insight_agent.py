"""Intención -> data por HTTP -> MCP -> HTML y revisiones, sin consumo LLM."""

import asyncio
import copy
import hashlib
import json
import time
from uuid import uuid4

import httpx

from inside_game.agents.contracts import DataResult
from inside_game.agents.dashboard_builder import DashboardBuilder, InsightLimits
from inside_game.agents.http_api import MAX_BODY, create_agent_app
from inside_game.agents.http_client import HttpDataAgent
from inside_game.insights.demo import demo_manifest
from inside_game.providers.models import ModelTurn

KEY = "only-local-test-credential-1234567890"
OTHER = "different-local-test-credential-1234567890"


def records():
    return [
        {
            "id": name,
            "name": name,
            "role": "agent",
            "expires_at": int(time.time()) + 3600,
            "sha256": hashlib.sha256(key.encode()).hexdigest(),
        }
        for name, key in [("one", KEY), ("two", OTHER)]
    ]


def fixture_result(request_id=None):
    return DataResult(
        request_id=request_id or uuid4(),
        status="complete",
        model="scripted-fixture",
        evidence=demo_manifest()["evidence"],
    )


class Model:
    name = "scripted-fixture"

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def respond(self, prompt, messages, tools):
        root = json.loads(messages[0]["content"])
        catalog = root["evidence_catalog"]
        intent = root["request"]["request_text"]
        if len(messages) > 1 and messages[-1].get("type") == "function_call_output":
            catalog = json.loads(messages[-1]["output"]).get(
                "evidence_catalog", catalog
            )
        if not catalog:
            name, args = (
                "request_data",
                {
                    "request_text": "Obtén tiros y red de pases del partido 900001.",
                    "context": {"match_ids": [900001]},
                },
            )
        else:
            plan = (
                copy.deepcopy(root["previous_plan"])
                if root["previous_plan"]
                else {
                    "title": "Informe de prueba",
                    "template_id": "match_overview",
                    "blocks": [
                        {
                            "id": "shots",
                            "insight_id": "shot_map",
                            "evidence_ids": [
                                e["evidence_id"]
                                for e in catalog
                                if e["operation"] == "get_shots"
                            ],
                        }
                    ],
                }
            )
            if "añade" in intent:
                plan["blocks"].append(
                    {
                        "id": "network",
                        "insight_id": "passing_network",
                        "evidence_ids": [
                            e["evidence_id"]
                            for e in catalog
                            if e["operation"] == "get_passing_network"
                        ],
                        "parameters": {"team_id": 1},
                    }
                )
            if "color" in intent:
                plan["teams"] = [{"team_id": 1, "color": "#5432ab"}]
            plan["analyst"] = {"text": "INVENTED MODEL ANALYSIS"}
            name, args = "render_report", plan
        return ModelTurn(
            [
                {
                    "type": "function_call",
                    "call_id": str(uuid4()),
                    "name": name,
                    "arguments": json.dumps(args),
                }
            ],
            10,
        )


def test_agent_uses_mcp_and_preserves_analyst_text_without_xss():
    async def run():
        request = {
            "request_text": "Crea página",
            "data_result": fixture_result(),
            "analyst": {"text": "Lectura original <script>alert(1)</script>"},
        }
        result = await DashboardBuilder(Model()).run(request)
        assert result.status == "complete", result.issues
        assert "Lectura original &lt;script&gt;" in result.html
        assert "INVENTED MODEL ANALYSIS" not in result.html
        assert result.plan.analyst.text == request["analyst"]["text"]
        assert (
            "html" not in result.model_dump() and "evidence" not in result.model_dump()
        )
        assert result.elapsed_ms < 55000 and result.model_turns == 1

    asyncio.run(run())


def test_http_delegation_create_modify_recolor_and_owner_isolation():
    async def run():
        seen = []

        async def data_runner(message, key, timeout):
            seen.append((message, key, timeout))
            return fixture_result(message.request_id)

        data_app = create_agent_app(credentials=records(), data_runner=data_runner)
        # Remote deployment requires HTTPS; ASGI test uses a localhost origin.
        # The production client enforces this same origin rule.
        app = create_agent_app(
            credentials=records(),
            model_factory=Model,
            data_base_url="http://localhost",
            data_transport=httpx.ASGITransport(app=data_app),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://localhost",
            headers={"Authorization": "Bearer " + KEY},
        ) as client:
            message = {
                "request_id": str(uuid4()),
                "request_text": "Crea página",
                "context": {"match_ids": [900001]},
                "analyst": {"text": "Texto original del analista."},
            }
            first = await client.post("/a2a/v1/insights", json=message)
            assert first.status_code == 200, first.text
            first = first.json()
            assert first["status"] == "complete", first
            assert first["revision"] == 1 and len(first["blocks"]) == 1
            assert len(seen) == 1 and seen[0][1] == KEY
            assert first["data_request_ids"] == [str(seen[0][0].request_id)]
            html = (await client.get(first["artifact_url"])).text
            assert "Texto original del analista." in html
            cached = (await client.post("/a2a/v1/insights", json=message)).json()
            assert cached == first and len(seen) == 1
            modified = (
                await client.post(
                    "/a2a/v1/insights",
                    json={
                        "request_text": "añade una red",
                        "report_id": first["report_id"],
                        "expected_revision": 1,
                    },
                )
            ).json()
            assert modified["revision"] == 2 and len(modified["blocks"]) == 2, modified
            assert len(seen) == 1
            colored = (
                await client.post(
                    "/a2a/v1/insights",
                    json={
                        "request_text": "cambia color",
                        "report_id": first["report_id"],
                        "expected_revision": 2,
                    },
                )
            ).json()
            assert colored["revision"] == 3 and len(colored["blocks"]) == 2
            assert len(seen) == 1
            latest = (await client.get(f"/a2a/v1/reports/{first['report_id']}")).json()
            assert latest["plan"]["teams"][0]["color"] == "#5432ab"
            assert latest["plan"]["analyst"]["text"] == "Texto original del analista."
            assert (await client.get(first["artifact_url"])).text == html
            stale = await client.post(
                "/a2a/v1/insights",
                json={
                    "request_text": "añade",
                    "report_id": first["report_id"],
                    "expected_revision": 1,
                },
            )
            assert stale.status_code == 409
            foreign = await client.get(
                first["artifact_url"], headers={"Authorization": "Bearer " + OTHER}
            )
            assert foreign.status_code == 404
            invalid = await client.post(
                "/a2a/v1/insights",
                json={"request_text": "crea", "url": "http://secret"},
            )
            assert invalid.status_code == 422 and "http://secret" not in invalid.text
            noauth = await client.get(
                first["artifact_url"], headers={"Authorization": ""}
            )
            assert noauth.status_code == 401

    asyncio.run(run())


def test_agent_deadline_stops_slow_model_without_artifact():
    class Slow(Model):
        async def respond(self, *args):
            await asyncio.sleep(1)

    async def run():
        result = await DashboardBuilder(
            Slow(), limits=InsightLimits(timeout_seconds=0.01)
        ).run({"request_text": "Crea", "data_result": fixture_result()})
        assert result.status == "error" and result.issues == ["DEADLINE_EXCEEDED"]
        assert result.html is None

    asyncio.run(run())


def test_http_body_limit_and_data_correlation():
    async def run():
        app = create_agent_app(credentials=records())
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://localhost",
            headers={"Authorization": "Bearer " + KEY},
        ) as client:
            r = await client.post("/a2a/v1/insights", content=b"x" * (MAX_BODY + 1))
            assert r.status_code == 413

        async def wrong(message, key, timeout):
            return fixture_result()  # Wrong request_id is not accepted by insights.

        app = create_agent_app(credentials=records(), data_runner=wrong)
        channel = HttpDataAgent(
            "http://localhost", KEY, transport=httpx.ASGITransport(app=app)
        )
        from inside_game.agents.contracts import DataRequest
        from inside_game.providers.models import ModelFailure

        try:
            await channel.fetch(DataRequest(request_text="tiros"), timeout=5)
        except ModelFailure as exc:
            assert exc.code == "DATA_AGENT_CORRELATION_MISMATCH"
        else:
            raise AssertionError("correlation mismatch accepted")

    asyncio.run(run())


def test_declarative_update_adds_configures_reorders_without_dropping_blocks():
    from inside_game.agents.insight_contracts import ReportChanges
    from inside_game.insights.contracts import ReportPlan

    manifest = demo_manifest()
    previous = ReportPlan.model_validate(
        {
            "title": "Anterior",
            "blocks": manifest["blocks"][:2],
            "teams": [{"team_id": 2, "color": "#ab3456"}],
        }
    )
    changed = ReportChanges.model_validate(
        {
            "add_blocks": [manifest["blocks"][4]],
            "teams": [{"team_id": 1, "color": "#123456"}],
        }
    ).apply(previous)
    assert len(changed.blocks) == 3 and changed.blocks[:2] == previous.blocks
    assert {t.team_id for t in changed.teams} == {1, 2}
    assert len(previous.blocks) == 2
    reordered = ReportChanges(order_ids=[b.id for b in reversed(changed.blocks)]).apply(
        changed
    )
    assert reordered.blocks == list(reversed(changed.blocks))


def test_patch_is_rendered_through_real_mcp_and_retains_analysis():
    from inside_game.insights.contracts import ReportPlan

    class Patch(Model):
        async def respond(self, prompt, messages, tools):
            block = demo_manifest()["blocks"][4]
            return ModelTurn(
                [
                    {
                        "type": "function_call",
                        "call_id": "patch",
                        "name": "update_report",
                        "arguments": json.dumps({"add_blocks": [block]}),
                    }
                ],
                5,
            )

    async def run():
        manifest = demo_manifest()
        previous = ReportPlan(
            title="Anterior",
            blocks=manifest["blocks"][:1],
            analyst={"text": "Análisis original"},
        )
        result = await DashboardBuilder(Patch()).run(
            {
                "request_text": "Añade la red",
                "report_id": str(uuid4()),
                "expected_revision": 1,
            },
            previous_plan=previous,
            previous_evidence=manifest["evidence"],
        )
        assert result.status == "complete", result.issues
        assert (
            len(result.plan.blocks) == 2 and result.plan.blocks[0] == previous.blocks[0]
        )
        assert (
            "Análisis original" in result.html
            and result.tool_trace[0]["tool"] == "update_report"
        )

    asyncio.run(run())


def test_invalid_patch_ids_rejected_instead_of_corrupting_previous_plan():
    import pytest

    from inside_game.agents.insight_contracts import ReportChanges
    from inside_game.insights.contracts import ReportPlan

    previous = ReportPlan(title="Anterior", blocks=demo_manifest()["blocks"][:1])
    for patch in [
        {"remove_block_ids": ["unknown"]},
        {"order_ids": []},
        {"add_blocks": [previous.blocks[0].model_dump()]},
    ]:
        with pytest.raises(ValueError):
            ReportChanges.model_validate(patch).apply(previous)
    assert len(previous.blocks) == 1


def test_simultaneous_modifications_publish_only_one_revision_and_failed_run_preserves_page():
    from inside_game.agents.insight_contracts import InsightRequest
    from inside_game.agents.report_store import ReportError, ReportStore

    async def run():
        store = ReportStore()
        request = InsightRequest(request_text="Crea", data_result=fixture_result())
        built = await DashboardBuilder(Model()).run(request)
        first = await store.publish("one", request, built)
        update = InsightRequest(
            request_text="configura", report_id=first.report_id, expected_revision=1
        )
        outcomes = await asyncio.gather(
            store.publish("one", update, built),
            store.publish("one", update, built),
            return_exceptions=True,
        )
        assert sum(isinstance(x, ReportError) for x in outcomes) == 1
        assert store.get("one", first.report_id).result.revision == 2
        assert store.get("one", first.report_id, 1).result.html == built.html
        assert first.plan == built.plan

    asyncio.run(run())


def test_aggregated_network_from_another_period_cannot_be_mislabeled_by_agent():
    from inside_game.insights.pages import compile_report

    manifest = demo_manifest()
    manifest["blocks"] = [
        b for b in manifest["blocks"] if b["insight_id"] == "passing_network"
    ]
    manifest["blocks"][0]["parameters"]["period"] = 2
    assert compile_report(manifest)[1][0].state == "incompatible"
