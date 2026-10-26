"""Arranque del agente de insights para procesos locales (CLI y página web).

Abre una vez lo costoso (cliente A2A o HTTP y modelo) y devuelve fábricas: cada
agente o cliente de datos nuevo nace sin caché, así un proceso largo no acumula
evidencia ni agota el presupuesto de un cliente compartido.
"""

import os
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import httpx

from inside_game.a2a_agents.common import open_a2a_client
from inside_game.dashboard.config import DashboardConfig
from inside_game.local_env import load_local_env, local_setting
from inside_game.tools.evidence_client import EvidenceClient, HttpTransport

from .agent import InsightsAgent
from .remote_data import A2ADataClient

ROOT = Path(__file__).resolve().parents[4]


def load_settings(root=ROOT):
    """Configuración privada del repo; el modelo sigue requiriendo elección explícita."""
    load_local_env(root)
    load_local_env(root, prefix="AZURE_")


def model_label():
    """Nombre del modelo elegido explícitamente, o None si no hay ninguno."""
    if not os.getenv("INSIDE_GAME_MODEL_PROVIDER"):
        return None
    if os.getenv("INSIDE_GAME_MODEL_PROVIDER") == "azure":
        return os.getenv("AZURE_OPENAI_DEPLOYMENT")
    if os.getenv("INSIDE_GAME_MODEL_PROVIDER") == "ollama":
        from inside_game.providers.ollama import DEFAULT_MODEL

        return os.getenv("INSIDE_GAME_OLLAMA_MODEL", DEFAULT_MODEL)
    return os.getenv("INSIDE_GAME_OPENCODE_MODEL")


@dataclass(frozen=True)
class Runtime:
    new_agent: object
    new_data: object
    model: str | None
    data_source: str


@asynccontextmanager
async def open_runtime(*, data_agent_url=None, use_model=True, root=ROOT):
    async with AsyncExitStack() as stack:
        if data_agent_url:
            token = local_setting("INSIDE_GAME_A2A_TOKEN", root) or None
            client = await stack.enter_async_context(
                open_a2a_client(data_agent_url, token=token)
            )

            def new_data():
                return A2ADataClient(client)

            source = f"agente de datos A2A ({data_agent_url})"
        else:
            config = DashboardConfig.load(root)
            http = await stack.enter_async_context(
                httpx.AsyncClient(
                    base_url=config.api_url,
                    headers={"Authorization": f"Bearer {config.api_key}"},
                    timeout=120,
                    follow_redirects=False,
                    trust_env=False,
                )
            )
            # Un transporte compartido mantiene el ritmo global frente a la API.
            transport = HttpTransport(http)

            def new_data():
                return EvidenceClient(transport)

            source = "API de datos (directa)"
        model = None
        # Sólo un modelo elegido explícitamente: create_model() caería en Azure por
        # defecto y AGENTS.md prohíbe seleccionar modelos automáticamente.
        if use_model and model_label():
            from inside_game.providers.models import create_model

            model = await stack.enter_async_context(create_model())

        def new_agent(data=None):
            return InsightsAgent(data or new_data(), model=model)

        yield Runtime(new_agent, new_data, model.name if model else None, source)
