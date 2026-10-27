import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from test_sports_analyst import KEY, records

from inside_game.agents.analyst_facts import evidence_facts
from inside_game.agents.contracts import DataResult
from inside_game.agents.evidence_pages import include_query_pages
from inside_game.agents.http_api import create_agent_app
from inside_game.agents.insights_http_client import HttpInsightsAgent
from inside_game.agents.report_changes import describe_changes
from inside_game.insights.contracts import ReportPlan
from inside_game.insights.demo import demo_manifest
from inside_game.workspace_snapshot import restore_snapshot


def test_diff_separates_a_cosmetic_change_from_new_data():
    spec = demo_manifest()
    old = ReportPlan.model_validate(
        {k: v for k, v in spec.items() if k in ReportPlan.model_fields}
    )
    renamed = old.model_copy(update={"title": "Nuevo título"}, deep=True)
    diff = describe_changes(old, renamed)
    assert diff["title_changed"] and not diff["data_changed_ids"]
    changed = renamed.model_copy(deep=True)
    changed.blocks[0].evidence_ids = [*changed.blocks[0].evidence_ids, "new-source"]
    diff = describe_changes(old, changed)
    assert diff["data_changed_ids"] == [changed.blocks[0].id]


def test_pagination_expansion_stays_within_the_exact_query_and_scope():
    spec = demo_manifest()
    plan = ReportPlan.model_validate(
        {k: v for k, v in spec.items() if k in ReportPlan.model_fields}
    )
    source = DataResult.model_validate(
        {
            "request_id": str(uuid4()),
            "status": "complete",
            "model": "fixture",
            "evidence": [spec["evidence"][0]],
        }
    ).evidence[0]
    first = source.model_copy(deep=True)
    first.evidence_id = "page1"
    first.query_id = "q1"
    second = first.model_copy(deep=True)
    second.evidence_id = "page2"
    second.arguments = {**first.arguments, "cursor": "next"}
    foreign = second.model_copy(deep=True)
    foreign.evidence_id = "foreign"
    foreign.arguments = {**first.arguments, "match_id": 900999}
    plan.blocks[0].evidence_ids = ["page1"]
    result = include_query_pages(plan, [first, second, foreign])
    assert result.blocks[0].evidence_ids == ["page1", "page2"]
    assert plan.blocks[0].evidence_ids == ["page1"]


def test_response_timeout_has_transport_grace_but_not_a_larger_server_budget(
    monkeypatch,
):
    captured = {}
    original = httpx.AsyncClient

    def factory(*args, **kwargs):
        captured["timeout"] = kwargs["timeout"]
        return original(*args, **kwargs)

    async def handle(request):
        captured["deadline"] = request.headers["x-agent-deadline-ms"]
        return httpx.Response(200, json={})

    monkeypatch.setattr(httpx, "AsyncClient", factory)

    async def run():
        client = HttpInsightsAgent(
            "http://127.0.0.1", KEY, transport=httpx.MockTransport(handle)
        )
        await client._request("POST", "/a2a/v1/insights", timeout=52, payload={})

    asyncio.run(run())
    assert captured == {"timeout": 54, "deadline": "52000"}


def test_local_backup_restoration_cannot_cross_credential_owners(tmp_path):
    path = tmp_path / "backup.json"
    path.write_text(
        json.dumps({"version": 1, "owner": "wrong-owner", "items": []}),
        encoding="utf-8",
    )
    app = create_agent_app(credentials=records())
    with pytest.raises(ValueError, match="OWNER_MISMATCH"):
        restore_snapshot(app, path, KEY)
    assert not app.state.chat.items and not app.state.store.pages


def test_xg_rankings_provide_sourced_values_without_synthesizing_missing_xg():
    result = DataResult.model_validate(
        {
            "request_id": str(uuid4()),
            "status": "complete",
            "model": "fixture",
            "evidence": [demo_manifest()["evidence"][0]],
        }
    )
    ev = result.evidence[0]
    ev.operation = "get_rankings"
    ev.arguments = {"entity_kind": "player", "metric": "xg"}
    ev.response.operation_id = "get_rankings"
    ev.response.data = {
        "metric": "xg",
        "normalization": "total",
        "items": [
            {
                "entity_id": 110,
                "value": 0.8,
                "total_value": 0.8,
                "rank": 1,
                "minutes": 90,
            },
            {
                "entity_id": 210,
                "value": None,
                "total_value": None,
                "rank": 2,
                "minutes": 90,
            },
        ],
    }
    facts = evidence_facts(result.evidence)
    assert any(f.path == "/data/items/0/value" and f.value == 0.8 for f in facts)
    assert not any(f.path == "/data/items/1/value" for f in facts)
