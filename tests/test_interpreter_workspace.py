"""Intención tipada, aislamiento de conversaciones y sesión del navegador."""

import asyncio
import json
import time
from uuid import UUID, uuid4

import httpx
import pytest
from test_sports_analyst import KEY, OTHER, records

from inside_game.access import KeyRegistry
from inside_game.agents.contracts import DataContext
from inside_game.agents.http_api import create_agent_app
from inside_game.agents.interpreter import Interpreter
from inside_game.providers.models import ModelFailure, ModelTurn
from inside_game.workspace import create_workspace


class Planner:
    name = "fixture"

    def __init__(self, action="clarify", ids=None):
        self.action, self.ids = action, ids or []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def respond(self, instructions, messages, tools):
        assert UUID(json.loads(messages[0]["content"])["request_id"])
        return ModelTurn(
            [
                {
                    "type": "function_call",
                    "name": "delegate_request",
                    "call_id": str(uuid4()),
                    "arguments": json.dumps(
                        {
                            "action": self.action,
                            "context": {"match_ids": self.ids},
                            "title": "Análisis",
                            "reply": "¿Qué partido quieres analizar?",
                        }
                    ),
                }
            ]
        )


def test_interpreter_refuses_invented_match_and_retains_clarification():
    async def run():
        args = {
            "text": "Analiza",
            "context": DataContext(),
            "history": [],
            "matches": [{"match_id": 900011}],
            "report": None,
        }
        assert (await Interpreter(Planner()).interpret(**args)).action == "clarify"
        with pytest.raises(ModelFailure, match="INTERPRETER_INVALID_PLAN"):
            await Interpreter(Planner(ids=[999999])).interpret(**args)

    asyncio.run(run())


@pytest.mark.parametrize("encoding", ["string_ids", "double_context"])
def test_plan_repairs_serialization_without_coercing_identity(encoding):
    class CorrectingPlanner(Planner):
        turns = 0

        async def respond(self, instructions, messages, tools):
            self.turns += 1
            output = await super().respond(instructions, messages, tools)
            args = json.loads(output.output[0]["arguments"])
            args["context"] = {"match_ids": [900011]}
            if self.turns == 1:
                args["context"] = (
                    {"match_ids": ["900011"]}
                    if encoding == "string_ids"
                    else json.dumps({"match_ids": [900011]})
                )
            else:
                error = json.loads(messages[-1]["output"])["error"]
                assert error["fields"][0]["path"] == ["context", "match_ids", 0]
            output.output[0]["arguments"] = json.dumps(args)
            return output

    async def run():
        model = CorrectingPlanner()
        agent = Interpreter(model)
        result = await agent.interpret(
            text="Analiza",
            context=DataContext(),
            history=[],
            matches=[{"match_id": 900011}],
            report=None,
        )
        assert result.context.match_ids == [900011]
        if encoding == "string_ids":
            assert model.turns == 2 and agent.trace[0]["status"] == "rejected"
        else:
            assert model.turns == 1 and agent.trace[0]["normalized_fields"] == [
                "context"
            ]

    asyncio.run(run())


def test_conversations_are_owned_and_jobs_are_idempotent():
    async def run():
        app = create_agent_app(credentials=records(), model_factory=Planner)
        engine = app.state.chat
        # Registros de prueba comparten los dueños definidos por el fixture.
        for _, _, principal in KeyRegistry(records()).entries:
            engine.catalogs[principal.id] = (
                time.monotonic() + 300,
                [{"match_id": 900011}],
            )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            a = {"Authorization": "Bearer " + KEY}
            b = {"Authorization": "Bearer " + OTHER}
            assert (await client.get("/a2a/v1/conversations")).status_code == 401
            cid = (await client.post("/a2a/v1/conversations", headers=a)).json()["id"]
            assert (
                await client.get("/a2a/v1/conversations/" + cid, headers=b)
            ).status_code == 404
            body = {"request_id": str(uuid4()), "text": "Analiza"}
            path = f"/a2a/v1/conversations/{cid}/messages"
            assert (await client.post(path, headers=a, json=body)).status_code == 202
            await asyncio.gather(*engine.tasks)
            assert (await client.post(path, headers=a, json=body)).status_code == 202
            assert (
                await client.post(path, headers=a, json={**body, "text": "otro"})
            ).status_code == 409
            result = (
                await client.get("/a2a/v1/conversations/" + cid, headers=a)
            ).json()
            assert len(result["messages"]) == 2 and result["stage"] == "clarification"
            assert result["runs"][0]["delegation"]["action"] == "clarify"
            assert KEY not in json.dumps(result)

    asyncio.run(run())


def test_browser_session_csrf_and_server_only_credentials(tmp_path):
    async def run():
        agent = create_agent_app(credentials=records())
        app = create_workspace(agent, frontend_dir=tmp_path, local_key=KEY)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as c:
            assert (await c.get("/workspace-api/conversations")).status_code == 401
            assert (await c.post("/workspace-api/session")).status_code == 403
            headers = {"X-Inside-Game": "workspace"}
            assert (
                await c.post(
                    "/workspace-api/session",
                    headers={**headers, "Origin": "http://evil.test"},
                )
            ).status_code == 403
            # testclient local is explicit; arbitrary network clients do not get local-demo access.
            response = await c.post(
                "/workspace-api/session",
                headers={**headers, "Authorization": "Bearer " + KEY},
            )
            assert response.status_code == 200 and KEY not in response.text
            assert (
                "HttpOnly" in response.headers["set-cookie"]
                and "SameSite=strict" in response.headers["set-cookie"]
            )
            response = await c.post("/workspace-api/conversations", headers=headers)
            assert response.status_code == 200 and KEY not in response.text
            assert (await c.get("/workspace-api/https://evil.test")).status_code == 404
            assert (
                await c.post(
                    "/workspace-api/conversations",
                    headers={**headers, "Origin": "http://evil.test"},
                )
            ).status_code == 403
            await c.delete("/workspace-api/session", headers=headers)
            assert (await c.get("/workspace-api/conversations")).status_code == 401

    asyncio.run(run())
