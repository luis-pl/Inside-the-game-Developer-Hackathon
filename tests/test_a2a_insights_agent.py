"""Cadena completa por A2A en memoria: cliente → insights → datos → API falsa.

Servidores A2A reales sobre ASGI; la API se sustituye por el fixture SINTÉTICO
de la galería con un contexto de partido completo. Sin red ni inferencia.
"""

import asyncio
import copy
import itertools
import json
import re
from contextlib import asynccontextmanager

import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers.proto_helpers import get_text_parts, new_message, new_text_message
from a2a.types import Role, SendMessageRequest, TaskState

from inside_game.a2a_agents import data_server, insights_server
from inside_game.a2a_agents.contracts import json_part
from inside_game.a2a_agents.insights_client import InsightsAgentClient
from inside_game.agents.insights_agent.agent import InsightsAgent
from inside_game.agents.insights_agent.contracts import AskRequest
from inside_game.agents.insights_agent.remote_data import A2ADataClient
from inside_game.insights.demo import demo_manifest
from inside_game.providers.models import ModelTurn

FIXTURE = {e["operation"]: e["response"] for e in demo_manifest()["evidence"]}
CONTEXT = {
    "match": {
        "match_id": 900001,
        "home_team_id": 1,
        "home_team_name": "Synthetic FC 1",
        "away_team_id": 2,
        "away_team_name": "Synthetic FC 2",
        "is_synthetic": True,
    },
    "lineups": [],
    "position_intervals": [],
    "periods": [{"period": 1, "home_attacks_positive_x": True, "duration_ms": 2700000}],
}
INTENT = {
    "template_id": "custom_report",
    "match_id": 900001,
    "insight_ids": ["shot_map"],
}
TOKEN = "t" * 40
CALL_IDS = itertools.count(1)


class FakeApi:
    def __init__(self):
        self.calls = []

    async def call(self, operation, arguments):
        self.calls.append(operation)
        response = copy.deepcopy(FIXTURE[operation])
        if operation == "get_match_context":
            response["data"] = copy.deepcopy(CONTEXT)
        return response, None


class ScriptedModel:
    name = "scripted"

    def __init__(self, *calls):
        self.calls = list(calls)

    async def respond(self, instructions, messages, tools):
        name, arguments = self.calls.pop(0)
        call = {
            "type": "function_call",
            "call_id": f"c{next(CALL_IDS)}",
            "name": name,
            "arguments": json.dumps(arguments),
        }
        return ModelTurn([call], 10)


class BrokenAgent:
    async def ask(self, request):
        raise RuntimeError("boom")


@asynccontextmanager
async def asgi_client(app, url, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url=url,
        headers=headers,
        timeout=30,
    ) as http:
        yield await create_client(
            url, client_config=ClientConfig(httpx_client=http, streaming=False)
        )


def chain(body, *, model=None, token=None, send_token=True, agent_factory=None):
    """Monta datos e insights por A2A y ejecuta `body(cliente_insights, a2a_crudo, api)`."""
    api = FakeApi()

    async def run():
        data_app = data_server.create_app(url="http://data/", transport=api)
        async with asgi_client(data_app, "http://data") as data:
            factory = agent_factory or (
                lambda: InsightsAgent(A2ADataClient(data), model=model)
            )
            insights_app = insights_server.create_app(
                url="http://insights/",
                agent_factory=factory,
                token=token,
            )
            async with asgi_client(
                insights_app, "http://insights", token if send_token else None
            ) as raw:
                return await body(InsightsAgentClient(raw), raw, api)

    return asyncio.run(run())


def test_intent_travels_the_whole_chain_and_returns_answer_and_report():
    async def body(client, _, api):
        return await client.ask({"intent": INTENT}), api.calls

    result, calls = chain(body)
    answer = result.answer
    assert answer.kind == "report" and answer.has_report
    assert "SINTÉTICO" in answer.summary and answer.labels.synthetic
    assert answer.blocks[0].insight_id == "shot_map" and answer.blocks[0].metrics
    assert "<svg" in result.report_html
    # El prefijo del mensaje A2A es interno: no ensucia métricas ni enlaces.
    html = result.report_html
    assert not re.search(r"<dt>a\d+-q\d+", html)
    assert not re.search(r"<summary>a\d+-q\d+-p\d+", html)
    assert not re.search(r">a\d+-q\d+-p\d+</a>", html)
    assert re.search(r">q\d+-p\d+</a>", html)
    # Los datos llegaron por el agente de datos, no por un atajo local.
    assert "get_match_context" in calls and "get_shots" in calls


def test_clients_that_do_not_accept_html_get_only_the_answer():
    async def body(_, raw, __):
        return await InsightsAgentClient(raw, want_report=False).ask({"intent": INTENT})

    result = chain(body)
    assert result.answer.has_report and result.report_html is None


def test_states_follow_the_answer_kind():
    async def state(raw, request):
        message = new_message([json_part(request)], role=Role.ROLE_USER)
        events = [
            e async for e in raw.send_message(SendMessageRequest(message=message))
        ]
        return events[-1].task.status.state

    async def body(_, raw, __):
        return (
            await state(raw, AskRequest(intent=INTENT)),
            await state(raw, AskRequest(question="¿Y el segundo tiempo?")),
        )

    report, no_model = chain(body)
    assert report == TaskState.TASK_STATE_COMPLETED
    assert no_model == TaskState.TASK_STATE_FAILED


def test_unexpected_agent_failure_is_reported_without_details():
    async def body(client, raw, __):
        result = await client.ask({"intent": INTENT})
        message = new_message(
            [json_part(AskRequest(intent=INTENT))], role=Role.ROLE_USER
        )
        events = [
            e async for e in raw.send_message(SendMessageRequest(message=message))
        ]
        return result, events[-1].task

    result, task = chain(body, agent_factory=lambda: BrokenAgent())
    assert task.status.state == TaskState.TASK_STATE_FAILED
    text = " ".join(get_text_parts(task.status.message.parts))
    assert "INSIGHTS_AGENT_FAILED" in text
    assert "boom" not in text
    assert result.answer.kind == "error"
    assert result.answer.issues == ["INSIGHTS_AGENT_FAILED"]
    assert "falló" in result.answer.summary.lower()


def test_clarification_is_input_required_and_the_follow_up_resolves():
    model = ScriptedModel(
        (
            "ask_clarification",
            {"question": "¿Qué partido?", "options": ["900001", "900003"]},
        ),
        ("submit_intent", INTENT),
    )

    async def body(client, _, api):
        first = await client.ask({"question": "El partido del Synthetic FC 1"})
        calls_after_first = list(api.calls)
        second = await client.ask(
            {"question": "el primero", "previous": first.answer.next.model_dump()}
        )
        return first, calls_after_first, second

    first, calls_after_first, second = chain(body, model=model)
    assert first.answer.kind == "clarification" and calls_after_first == []
    assert first.answer.next.question == "El partido del Synthetic FC 1"
    assert second.answer.kind == "report" and second.answer.intent.match_id == 900001


def test_a_message_that_is_not_an_ask_request_is_rejected():
    async def body(_, raw, api):
        message = new_text_message("dame un informe", role=Role.ROLE_USER)
        events = [
            e async for e in raw.send_message(SendMessageRequest(message=message))
        ]
        return events[-1].task.status.state, api.calls

    state, calls = chain(body)
    assert state == TaskState.TASK_STATE_REJECTED and calls == []


def test_token_protects_the_insights_agent_but_not_its_card():
    async def anonymous(client, _, api):
        return await client.ask({"intent": INTENT}), api.calls

    # create_client ya descubrió el AgentCard sin token: la tarjeta es pública.
    result, calls = chain(anonymous, token=TOKEN, send_token=False)
    assert result.answer.issues == ["INSIGHTS_AGENT_UNAVAILABLE"] and calls == []

    async def authorized(client, _, __):
        return await client.ask({"intent": INTENT})

    assert chain(authorized, token=TOKEN).answer.kind == "report"
