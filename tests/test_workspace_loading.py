"""Regressions for SQL waking from AutoPause and bounded catalog recovery."""

import asyncio
import json

import httpx
import pytest

from inside_game.agents.analyst_contracts import Fact, Statement
from inside_game.agents.analyst_facts import render_statement
from inside_game.agents.chat_http import Conversations
from inside_game.contracts import ApiResponse
from inside_game.providers.models import ModelFailure


def catalog_payload():
    return ApiResponse(
        operation_id="list_matches",
        method_id="fixture",
        request_id="test",
        scope={},
        data={
            "items": [
                {
                    "match_id": 900001,
                    "home_team_name": "Mock Objects FC",
                    "is_synthetic": True,
                }
            ]
        },
        provenance={},
        coverage={},
        coordinates={},
    ).model_dump(mode="json")


def install_transport(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        "inside_game.agents.chat_http.httpx.AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    monkeypatch.setenv("INSIDE_GAME_DATA_MCP_URL", "https://sports.example/mcp")
    monkeypatch.setenv("INSIDE_GAME_DATA_MCP_KEY", "fixture-key-" + "x" * 40)


@pytest.mark.parametrize("first", [429, 502, 503, 504, "timeout"])
def test_catalog_recovers_once_without_using_a_model(monkeypatch, first):
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.path == "/api/operations/list_matches"
        assert json.loads(request.content) == {"limit": 50}
        if len(calls) == 1:
            if first == "timeout":
                raise httpx.ReadTimeout("SQL is waking", request=request)
            return httpx.Response(first)
        return httpx.Response(200, json=catalog_payload())

    install_transport(monkeypatch, handler)

    async def run():
        engine = Conversations(None, None, None, None, None)
        result = await engine.catalog("owner", "private-test-key")
        assert result[0]["match_id"] == 900001
        assert len(calls) == 2
        assert await engine.catalog("owner", "private-test-key") == result
        assert len(calls) == 2
        assert calls[0].headers["authorization"] == "Bearer private-test-key"

    asyncio.run(run())


@pytest.mark.parametrize("status,attempts", [(401, 1), (403, 1), (503, 2)])
def test_catalog_does_not_loop_or_retry_unauthorized_requests(
    monkeypatch, status, attempts
):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status)

    install_transport(monkeypatch, handler)

    async def run():
        engine = Conversations(None, None, None, None, None)
        with pytest.raises(ModelFailure, match="MATCH_CATALOG_UNAVAILABLE"):
            await engine.catalog("owner", "fixture")
        assert len(calls) == attempts
        assert not engine.catalogs

    asyncio.run(run())


def test_catalog_rejects_wrong_operation_instead_of_caching_it(monkeypatch):
    payload = catalog_payload()
    payload["operation_id"] = "get_shots"
    install_transport(monkeypatch, lambda request: httpx.Response(200, json=payload))

    async def run():
        engine = Conversations(None, None, None, None, None)
        with pytest.raises(ModelFailure, match="INVALID_MATCH_CATALOG"):
            await engine.catalog("owner", "fixture")
        assert not engine.catalogs

    asyncio.run(run())


def test_pending_catalog_has_a_total_deadline(monkeypatch):
    original_timeout = asyncio.timeout

    async def handler(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json=catalog_payload())

    install_transport(monkeypatch, handler)
    monkeypatch.setattr(
        "inside_game.agents.chat_http.asyncio.timeout",
        lambda seconds: original_timeout(0.01),
    )

    async def run():
        engine = Conversations(None, None, None, None, None)
        with pytest.raises(ModelFailure, match="MATCH_CATALOG_UNAVAILABLE"):
            await engine.catalog("owner", "fixture")
        assert not engine.catalogs

    asyncio.run(run())


def test_concurrent_tabs_share_the_same_catalog_load(monkeypatch):
    calls = []

    async def handler(request):
        calls.append(request)
        await asyncio.sleep(0.01)
        return httpx.Response(200, json=catalog_payload())

    install_transport(monkeypatch, handler)

    async def run():
        engine = Conversations(None, None, None, None, None)
        rows = await asyncio.gather(
            *(engine.catalog("owner", "fixture") for _ in range(3))
        )
        assert rows[0] == rows[1] == rows[2]
        assert len(calls) == 1

    asyncio.run(run())


@pytest.mark.parametrize(
    "home,away,side,verb,valid",
    [
        (1, 2, "home", "ganó", False),
        (1, 2, "away", "ganó", True),
        (2, 1, "home", "ganó", True),
        (2, 1, "away", "perdió", True),
        (1, 1, "home", "ganó", False),
        (1, 1, "home", "empató", True),
        (2, 1, "home", "perdió", False),
    ],
)
def test_result_claims_cannot_invert_the_cited_score(home, away, side, verb, valid):
    values = {
        "home_team_name": "Mock Objects FC",
        "away_team_name": "Test Fixtures United",
        "home_score": home,
        "away_score": away,
    }
    facts = [
        Fact(
            id=f"f-{i:012x}",
            value=value,
            label=label,
            evidence_ids=["e-context"],
            operation="get_match_context",
            path="/data/match/" + label,
            scope={"match_id": 900001},
            provenance={"is_synthetic": True},
        )
        for i, (label, value) in enumerate(values.items())
    ]
    ids = {f.label: f.id for f in facts}
    statement = Statement(
        kind="observation",
        text="{{"
        + ids[side + "_team_name"]
        + "}} "
        + verb
        + " por {{"
        + ids["home_score"]
        + "}} a {{"
        + ids["away_score"]
        + "}}.",
        fact_ids=list(ids.values()),
    )
    if valid:
        assert verb in render_statement(statement, facts)
    else:
        with pytest.raises(ValueError, match="MATCH_RESULT_CONTRADICTS_SCORE"):
            render_statement(statement, facts)
