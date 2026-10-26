"""Servidor A2A del agente de insights: skill `ask_insight`.

Recibe un AskRequest (JSON) y devuelve dos artefactos: `answer` (InsightAnswer,
JSON pequeño) y `report` (HTML autocontenido) sólo si el cliente acepta
`text/html` en `accepted_output_modes`. Estados: informe o rechazo → COMPLETED,
aclaración → INPUT_REQUIRED, error → FAILED, mensaje no válido → REJECTED.
Sin sesiones: el cliente devuelve `answer.next` en la siguiente petición.

    python -m inside_game.a2a_agents.insights_server --port 8020 --data-agent-url http://127.0.0.1:8010

Los datos llegan del agente de datos por A2A. El modelo sólo se usa si
INSIDE_GAME_MODEL_PROVIDER está configurado explícitamente; si no, las preguntas
en texto responden MODEL_UNAVAILABLE y las intenciones funcionan igual.
"""

import argparse
import logging
import os
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from a2a.helpers.proto_helpers import (
    new_task_from_user_message,
    new_text_message,
    new_text_part,
)
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from pydantic import ValidationError
from starlette.applications import Starlette

from inside_game.agents.insights_agent.agent import InsightsAgent
from inside_game.agents.insights_agent.contracts import AskRequest
from inside_game.agents.insights_agent.remote_data import A2ADataClient
from inside_game.local_env import load_local_env, local_setting

from .common import LOOPBACK, BearerToken, BoundedTaskStore, open_a2a_client
from .contracts import HTML, JSON, json_part, read_json

log = logging.getLogger("inside_game.a2a.insights")
ASK_INSIGHT = "ask_insight"


def insights_agent_card(url):
    return AgentCard(
        name="inside-game-insights-agent",
        description=(
            "Agente de insights de Inside the game: convierte una pregunta o una "
            "intención en un informe visual de fútbol con su procedencia (datos "
            "reales anonimizados o SINTÉTICOS identificados) y una respuesta JSON."
        ),
        version="0.1.0",
        supported_interfaces=[
            AgentInterface(url=url, protocol_binding="JSONRPC", protocol_version="1.0")
        ],
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=[JSON],
        default_output_modes=[JSON, HTML],
        skills=[
            AgentSkill(
                id=ASK_INSIGHT,
                name="Preguntar por un insight",
                description=(
                    "Recibe AskRequest (JSON): `question` o `intent`, y `previous` "
                    "(el `next` de la respuesta anterior). Devuelve el artefacto "
                    "`answer` (InsightAnswer) y, si se acepta text/html, `report`."
                ),
                tags=["football", "insights", "report", "visualization"],
                input_modes=[JSON],
                output_modes=[JSON, HTML],
            )
        ],
    )


class AskInsightExecutor(AgentExecutor):
    def __init__(self, agent_factory=None):
        # Un agente por petición: sin estado compartido ni caché entre usuarios.
        self.agent_factory = agent_factory

    async def execute(self, context, event_queue):
        if context.current_task is None:
            await event_queue.enqueue_event(new_task_from_user_message(context.message))
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        try:
            request = read_json(context.message.parts, AskRequest)
        except (ValueError, ValidationError):
            await updater.reject(self._text("INVALID_ASK_REQUEST", context))
            return
        await updater.start_work()
        try:
            result = await self.agent_factory().ask(request)
        except Exception:
            # Frontera pública: el detalle queda en el log, no en la respuesta.
            log.exception("insights ask failed request=%s", request.request_id)
            await updater.failed(self._text("INSIGHTS_AGENT_FAILED", context))
            return
        answer = result.answer
        await updater.add_artifact([json_part(answer)], name="answer")
        if result.report_html and self._accepts_html(context):
            await updater.add_artifact(
                [new_text_part(result.report_html, media_type=HTML)], name="report"
            )
        message = self._text(answer.summary, context)
        if answer.kind == "clarification":
            await updater.requires_input(message)
        elif answer.kind == "error":
            await updater.failed(message)
        else:
            await updater.complete(message)

    async def cancel(self, context, event_queue):
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.cancel()

    @staticmethod
    def _accepts_html(context):
        modes = list(getattr(context.configuration, "accepted_output_modes", []) or [])
        return not modes or HTML in modes

    @staticmethod
    def _text(text, context):
        return new_text_message(
            text, context_id=context.context_id, task_id=context.task_id
        )


def create_app(
    *, url, agent_factory=None, data_agent_url=None, data_token=None, token=None
):
    executor = AskInsightExecutor(agent_factory)
    card = insights_agent_card(url)
    handler = DefaultRequestHandler(
        agent_executor=executor, task_store=BoundedTaskStore(), agent_card=card
    )

    @asynccontextmanager
    async def lifespan(app):
        if executor.agent_factory is not None:
            yield
            return
        async with AsyncExitStack() as stack:
            data = await stack.enter_async_context(
                open_a2a_client(data_agent_url, token=data_token)
            )
            model = None
            # Sólo un modelo elegido explícitamente (AGENTS.md): sin él, MODEL_UNAVAILABLE.
            if os.getenv("INSIDE_GAME_MODEL_PROVIDER"):
                from inside_game.providers.models import create_model

                model = await stack.enter_async_context(create_model())
            executor.agent_factory = lambda: InsightsAgent(
                A2ADataClient(data), model=model
            )
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
    parser.add_argument("--port", type=int, default=8020)
    parser.add_argument("--data-agent-url", default="http://127.0.0.1:8010")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    load_local_env(root)
    load_local_env(root, prefix="AZURE_")
    token = local_setting("INSIDE_GAME_A2A_TOKEN", root)
    if args.host not in LOOPBACK and len(token) < 32:
        parser.exit(
            1, "Fuera de loopback se requiere INSIDE_GAME_A2A_TOKEN (≥32 caracteres).\n"
        )
    app = create_app(
        url=f"http://{args.host}:{args.port}/",
        data_agent_url=args.data_agent_url,
        data_token=token or None,
        token=token or None,
    )
    print(f"Agente de insights A2A: http://{args.host}:{args.port}/", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
