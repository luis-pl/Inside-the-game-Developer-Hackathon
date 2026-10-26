"""Cliente A2A del agente de insights con la interfaz del agente local.

`ask()` devuelve el mismo AskResult que `InsightsAgent.ask()`: la CLI, el
intérprete o la UI pueden usar el agente local o el remoto sin cambios. Pide el
HTML sólo si `want_report`; sin él, el servidor no envía el informe.
"""

from contextlib import asynccontextmanager
from uuid import uuid4

from a2a.helpers.proto_helpers import get_text_parts, new_message
from a2a.types import Role, SendMessageConfiguration, SendMessageRequest, TaskState
from pydantic import ValidationError

from inside_game.agents.insights_agent.agent import AskResult, error_result
from inside_game.agents.insights_agent.contracts import AskRequest, InsightAnswer

from .common import open_a2a_client
from .contracts import HTML, JSON, json_part, read_json


class InsightsAgentClient:
    def __init__(self, client, *, want_report=True):
        self.client = client
        self.want_report = want_report

    async def ask(self, request: AskRequest | dict) -> AskResult:
        try:
            request = AskRequest.model_validate(request)
        except ValidationError:
            return error_result(uuid4(), "INVALID_REQUEST", None)
        modes = [JSON, HTML] if self.want_report else [JSON]
        message = new_message([json_part(request)], role=Role.ROLE_USER)
        try:
            events = [
                e
                async for e in self.client.send_message(
                    SendMessageRequest(
                        message=message,
                        configuration=SendMessageConfiguration(
                            accepted_output_modes=modes
                        ),
                    )
                )
            ]
        except Exception:  # noqa: BLE001 - red/SDK: nunca se reenvían detalles.
            return error_result(
                request.request_id, "INSIGHTS_AGENT_UNAVAILABLE", request.previous
            )
        task = events[-1].task if events and events[-1].HasField("task") else None
        if task is None or task.status.state == TaskState.TASK_STATE_REJECTED:
            return error_result(
                request.request_id, "INSIGHTS_AGENT_REJECTED", request.previous
            )
        artifacts = {a.name: a for a in task.artifacts}
        try:
            answer = read_json(artifacts["answer"].parts, InsightAnswer)
        except (KeyError, ValueError, ValidationError):
            # Una tarea FAILED sin `answer` es un fallo interno del servidor,
            # no una respuesta malformada del agente.
            code = (
                "INSIGHTS_AGENT_FAILED"
                if task.status.state == TaskState.TASK_STATE_FAILED
                else "INVALID_INSIGHTS_RESPONSE"
            )
            return error_result(request.request_id, code, request.previous)
        if answer.request_id != request.request_id:
            return error_result(
                request.request_id, "INVALID_INSIGHTS_RESPONSE", request.previous
            )
        report = (
            get_text_parts(artifacts["report"].parts) if "report" in artifacts else []
        )
        return AskResult(answer, report[0] if report else None)


@asynccontextmanager
async def connect_insights_agent(url, *, token=None, want_report=True, timeout=600):
    async with open_a2a_client(url, token=token, timeout=timeout) as client:
        yield InsightsAgentClient(client, want_report=want_report)
