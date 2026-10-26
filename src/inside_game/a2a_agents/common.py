"""Piezas compartidas por los servidores y clientes A2A del proyecto."""

import hmac
from collections import OrderedDict
from contextlib import asynccontextmanager

import httpx
from a2a.client import ClientConfig, create_client
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import TaskState
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

LOOPBACK = {"127.0.0.1", "localhost", "::1"}
# Sin sesiones: una tarea que espera aclaración tampoco se reanuda por su ID.
FINISHED = {
    TaskState.TASK_STATE_COMPLETED,
    TaskState.TASK_STATE_FAILED,
    TaskState.TASK_STATE_CANCELED,
    TaskState.TASK_STATE_REJECTED,
    TaskState.TASK_STATE_INPUT_REQUIRED,
}


class BoundedTaskStore(InMemoryTaskStore):
    """Conserva sólo las últimas tareas terminadas.

    El InMemoryTaskStore del SDK guarda cada tarea con sus artefactos para
    siempre: varios MB de evidencia o de HTML por petición. Los agentes no
    guardan estado entre peticiones, así que basta un historial corto.
    """

    def __init__(self, max_finished=16):
        super().__init__()
        self.max_finished = max_finished
        self._finished = OrderedDict()

    async def save(self, task, context):
        await super().save(task, context)
        if task.status.state not in FINISHED:
            self._finished.pop(task.id, None)
            return
        self._finished[task.id] = context
        self._finished.move_to_end(task.id)
        while len(self._finished) > self.max_finished:
            task_id, owner_context = self._finished.popitem(last=False)
            await self.delete(task_id, owner_context)


class BearerToken(BaseHTTPMiddleware):
    """Protege JSON-RPC; el AgentCard es público por diseño del protocolo."""

    def __init__(self, app, token):
        super().__init__(app)
        self.expected = ("Bearer " + token).encode()

    async def dispatch(self, request, call_next):
        if request.method == "POST":
            given = request.headers.get("authorization", "").encode()
            if not hmac.compare_digest(given, self.expected):
                return JSONResponse(
                    {"error": {"code": "UNAUTHORIZED"}}, status_code=401
                )
        return await call_next(request)


@asynccontextmanager
async def open_a2a_client(url, *, token=None, timeout=180):
    """Descubre el AgentCard y abre un cliente; el token nunca va en la URL."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(
        headers=headers, timeout=timeout, follow_redirects=False, trust_env=False
    ) as http:
        yield await create_client(
            url, client_config=ClientConfig(httpx_client=http, streaming=False)
        )
