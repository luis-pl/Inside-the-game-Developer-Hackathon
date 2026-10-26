"""Agente de datos por A2A (execute_plan) y su cliente en el agente de insights.

Servidor y cliente A2A reales en memoria; la API se sustituye por el fixture
SINTÉTICO de la galería. Sin red ni LLM.
"""

import asyncio
import copy

import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers.proto_helpers import new_text_message
from a2a.types import Role, SendMessageRequest, TaskState

from inside_game.a2a_agents.data_server import create_app
from inside_game.agents.insights_agent.composer import compose
from inside_game.agents.insights_agent.contracts import (
    BlockPlan,
    InsightIntent,
    PlanLabels,
    QuerySpec,
    ResolvedPlan,
)
from inside_game.agents.insights_agent.remote_data import A2ADataClient
from inside_game.insights.demo import demo_manifest
from inside_game.tools.evidence_client import EvidenceClient

FIXTURE = {e["operation"]: e["response"] for e in demo_manifest()["evidence"]}
TOKEN = "t" * 40


class FakeApi:
    def __init__(self, errors=None):
        self.errors = errors or {}
        self.calls = []

    async def call(self, operation, arguments):
        self.calls.append(operation)
        if operation in self.errors:
            return None, self.errors[operation]
        return copy.deepcopy(FIXTURE[operation]), None


def with_agent(body, *, api=None, token=None, send_token=True):
    api = api or FakeApi()
    app = create_app(url="http://test/", transport=api, token=token)

    async def run():
        headers = {"Authorization": f"Bearer {token}"} if token and send_token else {}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers=headers,
            timeout=30,
        ) as http:
            client = await create_client(
                "http://test",
                client_config=ClientConfig(httpx_client=http, streaming=False),
            )
            return await body(A2ADataClient(client), http)

    return asyncio.run(run()), api


def queries(*specs):
    return [QuerySpec(key=k, operation=o, arguments=a) for k, o, a in specs]


SHOTS = ("s", "get_shots", {"match_id": 900001, "limit": 200})
PASSES = ("p", "get_passes", {"match_id": 900001, "limit": 200})


def test_plan_runs_over_a2a_with_exact_types_and_session_cache():
    async def body(data, _):
        first = await data.run(queries(SHOTS, PASSES))
        again = await data.run(queries(SHOTS))
        return first, again, data

    (first, again, data), api = with_agent(body)
    assert first["s"][1] is None and first["p"][1] is None
    assert again["s"] == first["s"]
    # Una sola llamada A2A y una consulta a la API por operación.
    assert data.calls == 1 and sorted(api.calls) == ["get_passes", "get_shots"]
    evidence = data.evidence[first["s"][0][0]]
    assert evidence["evidence_id"] == "q1-p1"
    # JSON como texto: los enteros llegan enteros, no 900001.0.
    assert evidence["arguments"]["match_id"] == 900001
    assert type(evidence["arguments"]["match_id"]) is int


def test_query_errors_travel_per_query_without_hiding_the_rest():
    async def body(data, _):
        return await data.run(
            queries(SHOTS, ("l", "get_line_breaks", {"match_id": 900001, "team_id": 1}))
        )

    results, _ = with_agent(
        body, api=FakeApi(errors={"get_line_breaks": "SOURCE_FIELD_UNAVAILABLE"})
    )
    assert results["s"][1] is None and results["s"][0]
    assert results["l"] == ([], "SOURCE_FIELD_UNAVAILABLE")


def test_invalid_arguments_are_rejected_locally_before_any_message():
    async def body(data, _):
        result = await data.run(
            queries(("x", "get_shots", {"match_id": "nope"}), ("y", "drop", {}))
        )
        return result, data.calls

    (result, calls), api = with_agent(body)
    assert result == {
        "x": ([], "INVALID_ARGUMENT"),
        "y": ([], "UNREGISTERED_OPERATION"),
    }
    assert calls == 0 and api.calls == []


def test_a_message_that_is_not_a_plan_is_rejected():
    async def body(data, _):
        message = new_text_message("dame todos los datos", role=Role.ROLE_USER)
        events = [
            e
            async for e in data.client.send_message(SendMessageRequest(message=message))
        ]
        return events[-1].task.status.state

    state, api = with_agent(body)
    assert state == TaskState.TASK_STATE_REJECTED and api.calls == []


def test_token_protects_json_rpc_but_not_the_agent_card():
    async def anonymous(data, http):
        card = await http.get("/.well-known/agent-card.json")
        result = await data.run(queries(SHOTS))
        return card.status_code, result

    (card_status, result), api = with_agent(anonymous, token=TOKEN, send_token=False)
    assert card_status == 200
    assert result["s"] == ([], "DATA_AGENT_UNAVAILABLE") and api.calls == []

    async def authorized(data, _):
        return await data.run(queries(SHOTS))

    result, _ = with_agent(authorized, token=TOKEN)
    assert result["s"][1] is None


def test_composer_builds_the_report_through_a2a():
    plan = ResolvedPlan(
        intent=InsightIntent(template_id="match_overview", match_id=900001),
        source="synthetic",
        labels=PlanLabels(
            match="Synthetic FC 1 vs Synthetic FC 2",
            home_team="Synthetic FC 1",
            away_team="Synthetic FC 2",
            focus_team="Synthetic FC 1",
            synthetic=True,
        ),
        queries=queries(SHOTS, PASSES),
        blocks=[
            BlockPlan(
                id="shots",
                insight_id="shot_map",
                title="Tiros",
                query_keys=["s"],
                parameters={},
            ),
            BlockPlan(
                id="passes",
                insight_id="pass_map",
                title="Pases",
                query_keys=["p"],
                parameters={},
            ),
        ],
        home_team_id=1,
        away_team_id=2,
        focus_team_id=1,
    )

    async def body(data, _):
        return await compose(plan, data, title="Informe SINTÉTICO por A2A")

    result, _ = with_agent(body)
    assert [b.id for b in result.blocks] == ["shots", "passes"]
    assert "Informe SINTÉTICO por A2A" in result.html
    # Las métricas se llaman igual por A2A que en local, aunque cambien los IDs.
    local = asyncio.run(compose(plan, EvidenceClient(FakeApi()), title="local"))
    assert [b.metrics for b in result.blocks] == [b.metrics for b in local.blocks]
    assert result.blocks[0].evidence_ids == ["q1-p1"]


def test_evidence_ids_stay_unique_across_messages():
    # El agente de datos numera desde q1 en cada mensaje: la sesión no debe repetir IDs.
    async def body(data, _):
        first = await data.run(queries(SHOTS))
        second = await data.run(queries(PASSES))
        return first["s"][0] + second["p"][0], data

    (ids, data), _ = with_agent(body)
    assert data.calls == 2
    assert ids == ["q1-p1", "q2-p1"] and set(ids) == set(data.evidence)
