"""Servidor A2A del agente de datos: skill `execute_plan`.

Envuelve el acceso a datos sin modificar `agents/data_agent.py`. Ejecuta un plan
de consultas exactas contra la API (validación, paginación, identidad y
procedencia de cada respuesta) y devuelve la evidencia original. No usa LLM.
La skill en lenguaje natural del agente de datos se añadirá cuando haya modelo.

    python -m inside_game.a2a_agents.data_server --port 8010

Autenticación: si existe INSIDE_GAME_A2A_TOKEN, el endpoint JSON-RPC exige
`Authorization: Bearer <token>`. Sin token sólo escucha en loopback.
"""

import argparse
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from a2a.helpers.proto_helpers import new_task_from_user_message, new_text_message
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from pydantic import ValidationError
from starlette.applications import Starlette

from inside_game.dashboard.config import DashboardConfig
from inside_game.local_env import local_setting
from inside_game.tools.evidence_client import (
    EvidenceClient,
    HttpTransport,
)

from .common import LOOPBACK, BearerToken, BoundedTaskStore
from .contracts import (
    EXECUTE_PLAN,
    JSON,
    ExecutePlanRequest,
    PlanResult,
    QueryOutcome,
    json_part,
    read_json,
)

log = logging.getLogger("inside_game.a2a.data")


def data_agent_card(url):
    return AgentCard(
        name="inside-game-data-agent",
        description=(
            "Agente de datos de Inside the game: ejecuta consultas registradas de "
            "fútbol y devuelve evidencia original con procedencia (datos reales "
            "anonimizados y SINTÉTICOS identificados)."
        ),
        version="0.1.0",
        supported_interfaces=[
            AgentInterface(url=url, protocol_binding="JSONRPC", protocol_version="1.0")
        ],
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=[JSON],
        default_output_modes=[JSON],
        skills=[
            AgentSkill(
                id=EXECUTE_PLAN,
                name="Ejecutar plan de consultas",
                description=(
                    "Recibe ExecutePlanRequest (JSON) con consultas exactas "
                    "{key, operation, arguments} y devuelve PlanResult con la "
                    "evidencia de cada consulta. Sin LLM."
                ),
                tags=["football", "data", "evidence"],
                input_modes=[JSON],
                output_modes=[JSON],
            )
        ],
    )


class ExecutePlanExecutor(AgentExecutor):
    def __init__(self, transport=None):
        # Un transporte compartido mantiene el ritmo global frente a la API;
        # cada petición usa su propio cliente y presupuesto de evidencia.
        self.transport = transport

    async def execute(self, context, event_queue):
        if context.current_task is None:
            await event_queue.enqueue_event(new_task_from_user_message(context.message))
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        try:
            request = read_json(context.message.parts, ExecutePlanRequest)
        except (ValueError, ValidationError):
            await updater.reject(self._text("INVALID_PLAN_REQUEST", context))
            return
        await updater.start_work()
        try:
            data = EvidenceClient(self.transport)
            results = await data.run(request.queries)
        except Exception:
            # Frontera pública: el detalle queda en el log del servidor, no en la respuesta.
            log.exception("execute_plan failed request=%s", request.request_id)
            await updater.failed(self._text("DATA_AGENT_FAILED", context))
            return
        errors = sum(1 for _, error in results.values() if error)
        result = PlanResult(
            request_id=request.request_id,
            status="complete"
            if not errors
            else "error"
            if errors == len(results)
            else "partial",
            results={
                key: QueryOutcome(evidence_ids=ids, error=error)
                for key, (ids, error) in results.items()
            },
            evidence=[
                data.evidence[i]
                for ids, _ in results.values()
                for i in dict.fromkeys(ids)
            ],
        )
        await updater.add_artifact([json_part(result)], name="plan_result")
        await updater.complete()

    async def cancel(self, context, event_queue):
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.cancel()

    @staticmethod
    def _text(code, context):
        return new_text_message(
            code, context_id=context.context_id, task_id=context.task_id
        )


def create_app(*, url, transport=None, api_config=None, token=None):
    executor = ExecutePlanExecutor(transport)
    card = data_agent_card(url)
    handler = DefaultRequestHandler(
        agent_executor=executor, task_store=BoundedTaskStore(), agent_card=card
    )

    @asynccontextmanager
    async def lifespan(app):
        if executor.transport is not None:
            yield
            return
        async with httpx.AsyncClient(
            base_url=api_config.api_url,
            headers={"Authorization": f"Bearer {api_config.api_key}"},
            timeout=120,
            follow_redirects=False,
            trust_env=False,
        ) as http:
            executor.transport = HttpTransport(http)
            yield

    app = Starlette(
        routes=create_agent_card_routes(card)
        + create_jsonrpc_routes(handler, rpc_url="/"),
        lifespan=lifespan,
    )
    if token:
        app.add_middleware(BearerToken, token=token)
    return app


def main():
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    token = local_setting("INSIDE_GAME_A2A_TOKEN", root)
    if args.host not in LOOPBACK and len(token) < 32:
        parser.exit(
            1, "Fuera de loopback se requiere INSIDE_GAME_A2A_TOKEN (≥32 caracteres).\n"
        )
    app = create_app(
        url=f"http://{args.host}:{args.port}/",
        api_config=DashboardConfig.load(root),
        token=token or None,
    )
    print(f"Agente de datos A2A: http://{args.host}:{args.port}/", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
