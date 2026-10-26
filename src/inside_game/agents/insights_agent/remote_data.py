"""Cliente A2A del agente de datos con la interfaz del cliente in-process.

El resolvedor y el compositor no distinguen transporte: `fetch`, `query`,
`run` y `evidence` funcionan igual. Las consultas sin caché de un `run` viajan
en un único mensaje `execute_plan`. Las consultas se renumeran para toda la
sesión (q1, q2…): el agente de datos numera desde cero en cada mensaje y dos
evidencias distintas no deben compartir ID en un informe. Cada evidencia se
revalida con el contrato local antes de usarse.
"""

import itertools
import json
from contextlib import asynccontextmanager

from a2a.helpers.proto_helpers import new_message
from a2a.types import Role, SendMessageRequest, TaskState
from pydantic import ValidationError

from inside_game.a2a_agents.common import open_a2a_client
from inside_game.a2a_agents.contracts import (
    ExecutePlanRequest,
    PlanQuery,
    PlanResult,
    json_part,
    read_json,
)
from inside_game.agents.contracts import Evidence
from inside_game.service import OPERATIONS


class A2ADataClient:
    def __init__(self, client):
        self.client = client
        self.evidence: dict[str, dict] = {}
        self.queries: dict[str, tuple[list[str], str | None]] = {}
        self.calls = 0
        # Numeración propia de la sesión; la del agente de datos se reinicia por mensaje.
        self._query_ids = itertools.count(1)

    async def fetch(self, operation, arguments):
        ids, error = await self.query(operation, arguments)
        return [self.evidence[i] for i in ids], error

    async def query(self, operation, arguments):
        return (await self._resolve([("single", operation, arguments)]))["single"]

    async def run(self, queries):
        return await self._resolve([(q.key, q.operation, q.arguments) for q in queries])

    async def _resolve(self, queries):
        identities, pending, results = {}, {}, {}
        for key, operation, arguments in queries:
            if operation not in OPERATIONS:
                results[key] = ([], "UNREGISTERED_OPERATION")
                continue
            try:
                checked = (
                    OPERATIONS[operation]
                    .model_validate(arguments)
                    .model_dump(mode="json")
                )
            except ValidationError:
                results[key] = ([], "INVALID_ARGUMENT")
                continue
            identity = operation + json.dumps(checked, sort_keys=True)
            identities[key] = identity
            if identity not in self.queries:
                pending.setdefault(identity, (operation, checked))
        if pending:
            await self._send(pending)
        for key, identity in identities.items():
            results[key] = self.queries[identity]
        return results

    async def _send(self, pending):
        plan = ExecutePlanRequest(
            queries=[
                PlanQuery(key=f"k{n}", operation=operation, arguments=arguments)
                for n, (operation, arguments) in enumerate(pending.values(), 1)
            ]
        )
        keys = dict(zip((q.key for q in plan.queries), pending, strict=True))
        local_queries = {}
        self.calls += 1
        result = await self._exchange(plan)
        if isinstance(result, str):
            for identity in pending:
                self.queries[identity] = ([], result)
            return
        received = {e.evidence_id: e for e in result.evidence}
        for key, identity in keys.items():
            outcome = result.results.get(key)
            if outcome is None:
                self.queries[identity] = ([], "MISSING_QUERY_RESULT")
            elif outcome.error:
                self.queries[identity] = ([], outcome.error)
            elif not set(outcome.evidence_ids) <= set(received):
                # Una consulta con páginas ausentes no se presenta como completa.
                self.queries[identity] = ([], "MISSING_EVIDENCE")
            else:
                self.queries[identity] = (
                    [
                        self._store(received[i], local_queries)
                        for i in outcome.evidence_ids
                    ],
                    None,
                )

    def _store(self, evidence, local_queries):
        """Guarda la evidencia con IDs únicos en la sesión y devuelve el ID local.

        `q3-p2` del mensaje → `q17-p2` en la sesión: se conserva el sufijo de página.
        """
        query_id = local_queries.setdefault(
            evidence.query_id, f"q{next(self._query_ids)}"
        )
        page = evidence.evidence_id.removeprefix(evidence.query_id)
        local = Evidence.model_validate(
            {
                **evidence.model_dump(mode="json"),
                "evidence_id": query_id
                + (
                    page if page != evidence.evidence_id else "-" + evidence.evidence_id
                ),
                "query_id": query_id,
            }
        )
        self.evidence[local.evidence_id] = local.model_dump(mode="json")
        return local.evidence_id

    async def _exchange(self, plan):
        """Envía el plan; devuelve PlanResult o un código de error."""
        message = new_message([json_part(plan)], role=Role.ROLE_USER)
        try:
            events = [
                e
                async for e in self.client.send_message(
                    SendMessageRequest(message=message)
                )
            ]
        except Exception:  # noqa: BLE001 - red/SDK: nunca se reenvían detalles.
            return "DATA_AGENT_UNAVAILABLE"
        task = events[-1].task if events and events[-1].HasField("task") else None
        if task is None:
            return "DATA_AGENT_NO_TASK"
        if task.status.state != TaskState.TASK_STATE_COMPLETED:
            return "DATA_AGENT_" + TaskState.Name(task.status.state).removeprefix(
                "TASK_STATE_"
            )
        try:
            result = read_json(task.artifacts[0].parts, PlanResult)
        except (IndexError, ValueError, ValidationError):
            return "INVALID_DATA_AGENT_RESPONSE"
        if result.request_id != plan.request_id:
            return "INVALID_DATA_AGENT_RESPONSE"
        return result


@asynccontextmanager
async def connect_data_agent(url, *, token=None, timeout=180):
    """Cliente del agente de datos para una sesión; la caché vive con él."""
    async with open_a2a_client(url, token=token, timeout=timeout) as client:
        yield A2ADataClient(client)
