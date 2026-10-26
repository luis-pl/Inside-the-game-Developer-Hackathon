"""Contrato del SDK A2A (a2a-sdk 1.2.3) del que dependen los agentes, sin red.

Fija lo aprendido en la prueba mínima: descubrimiento del AgentCard, tareas
completadas con artefactos, `input-required` para aclaraciones en el mismo
contexto, cargas de varios MB y la razón para enviar JSON como texto: un
DataPart viaja como google.protobuf.Value y convierte los enteros en double.
"""

import asyncio
import json

import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers.proto_helpers import (
    get_data_parts,
    get_text_parts,
    new_data_part,
    new_message,
    new_task_from_user_message,
    new_text_message,
    new_text_part,
)
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Role,
    SendMessageRequest,
    TaskState,
)
from starlette.applications import Starlette

JSON = "application/json"


class Echo(AgentExecutor):
    """Informa de los tipos recibidos; pide aclaración ante 'ambiguo'."""

    async def execute(self, context, event_queue):
        if context.current_task is None:
            await event_queue.enqueue_event(new_task_from_user_message(context.message))
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.start_work()
        texts = get_text_parts(context.message.parts)
        if texts == ["ambiguo"]:
            question = new_text_message(
                "¿Qué partido?", context_id=context.context_id, task_id=context.task_id
            )
            await updater.requires_input(question)
            return
        data = get_data_parts(context.message.parts)
        report = {
            "data_part": {
                k: type(v).__name__ for k, v in (data[0] if data else {}).items()
            },
            "json_text": {k: type(v).__name__ for k, v in json.loads(texts[0]).items()}
            if texts and texts[0].startswith("{")
            else {},
            "payload": "x" * (3 * 1024 * 1024) if texts == ["grande"] else "",
        }
        await updater.add_artifact(
            [new_text_part(json.dumps(report), media_type=JSON)], name="result"
        )
        await updater.complete()

    async def cancel(self, context, event_queue):
        raise NotImplementedError


CARD = AgentCard(
    name="eco",
    description="Agente de prueba",
    version="0.0.1",
    supported_interfaces=[
        AgentInterface(
            url="http://test/", protocol_binding="JSONRPC", protocol_version="1.0"
        )
    ],
    capabilities=AgentCapabilities(streaming=False),
    default_input_modes=[JSON, "text/plain"],
    default_output_modes=[JSON],
    skills=[
        AgentSkill(id="eco", name="Eco", description="Devuelve tipos", tags=["test"])
    ],
)


def scenario(body):
    async def run():
        handler = DefaultRequestHandler(
            agent_executor=Echo(), task_store=InMemoryTaskStore(), agent_card=CARD
        )
        app = Starlette(
            routes=create_agent_card_routes(CARD)
            + create_jsonrpc_routes(handler, rpc_url="/")
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=30
        ) as http:
            client = await create_client(
                "http://test",
                client_config=ClientConfig(httpx_client=http, streaming=False),
            )

            async def send(parts, context_id=None):
                message = new_message(parts, context_id=context_id, role=Role.ROLE_USER)
                events = [
                    e
                    async for e in client.send_message(
                        SendMessageRequest(message=message)
                    )
                ]
                return events[-1].task

            return await body(send)

    return asyncio.run(run())


def artifact(task):
    return json.loads(get_text_parts(task.artifacts[0].parts)[0])


def test_card_is_discovered_and_task_completes_with_a_json_artifact():
    async def body(send):
        return await send([new_text_part("{}", media_type=JSON)])

    task = scenario(body)
    assert task.status.state == TaskState.TASK_STATE_COMPLETED
    assert artifact(task)["payload"] == ""


def test_data_parts_turn_integers_into_floats_so_contracts_travel_as_json_text():
    async def body(send):
        return await send(
            [
                new_data_part({"match_id": 900001}),
                new_text_part(json.dumps({"match_id": 900001}), media_type=JSON),
            ]
        )

    report = artifact(scenario(body))
    assert report["data_part"] == {"match_id": "float"}
    assert report["json_text"] == {"match_id": "int"}


def test_clarification_uses_input_required_and_the_follow_up_keeps_the_context():
    async def body(send):
        asked = await send([new_text_part("ambiguo")])
        follow = await send([new_text_part("grande")], context_id=asked.context_id)
        return asked, follow

    asked, follow = scenario(body)
    assert asked.status.state == TaskState.TASK_STATE_INPUT_REQUIRED
    assert get_text_parts(asked.status.message.parts) == ["¿Qué partido?"]
    assert follow.context_id == asked.context_id
    # La evidencia de un plan puede ocupar varios MB.
    assert len(artifact(follow)["payload"]) == 3 * 1024 * 1024


def test_bounded_store_forgets_old_finished_tasks_but_keeps_running_ones():
    from a2a.server.context import ServerCallContext
    from a2a.types import Task, TaskStatus

    from inside_game.a2a_agents.common import BoundedTaskStore

    async def run():
        store, context = BoundedTaskStore(max_finished=3), ServerCallContext()

        def task(n, state):
            return Task(id=f"t{n}", context_id="c", status=TaskStatus(state=state))

        await store.save(task(0, TaskState.TASK_STATE_WORKING), context)
        for n in range(1, 6):
            await store.save(task(n, TaskState.TASK_STATE_COMPLETED), context)
        return [await store.get(f"t{n}", context) is not None for n in range(6)]

    # La tarea en curso sigue; de las terminadas sólo quedan las tres últimas.
    assert asyncio.run(run()) == [True, False, False, True, True, True]
