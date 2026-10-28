"""NVIDIA NIM alojado (build.nvidia.com) mediante su API compatible con Chat Completions.

El destino es fijo: el endpoint gratuito de NVIDIA. La clave individual se lee
del entorno, nunca del prompt. El razonamiento del modelo se activa sólo de forma
explícita con INSIDE_GAME_NIM_THINKING=1. No se usan endpoints de socios de pago
ni se cambia a otro proveedor ante un error.
"""

import os
from dataclasses import dataclass, field

from inside_game.providers.models import AzureChatModel

NIM_ENDPOINT = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"


@dataclass(frozen=True)
class NimModelSettings:
    api_key: str = field(default="", repr=False)
    deployment: str = DEFAULT_MODEL
    thinking: bool = False
    api: str = "chat_completions"
    max_output_tokens: int = 4096
    timeout_seconds: float = 120
    endpoint: str = NIM_ENDPOINT
    provider: str = "nim"
    # Compatibilidad con el adaptador compartido; no se envía a NIM.
    reasoning_effort: str = "none"

    def __post_init__(self):
        if self.endpoint != NIM_ENDPOINT:
            raise ValueError("Use the official NVIDIA NIM endpoint")
        if (
            not isinstance(self.api_key, str)
            or not self.api_key
            or self.api_key.strip() != self.api_key
            or any(c in self.api_key for c in "\r\n")
        ):
            raise ValueError("NVIDIA NIM API key is missing or invalid")
        if (
            not isinstance(self.deployment, str)
            or "/" not in self.deployment
            or self.deployment.strip() != self.deployment
        ):
            raise ValueError("Configure the NIM model as organization/model")
        if self.api != "chat_completions":
            raise ValueError("NVIDIA NIM only supports the chat_completions API")
        if not 256 <= self.max_output_tokens <= 16384:
            raise ValueError("Invalid model output budget")
        if not 0 < self.timeout_seconds <= 600:
            raise ValueError("Invalid model timeout")

    @classmethod
    def from_env(cls):
        return cls(
            api_key=os.getenv("INSIDE_GAME_NIM_API_KEY", ""),
            deployment=os.getenv("INSIDE_GAME_NIM_MODEL", DEFAULT_MODEL),
            thinking=os.getenv("INSIDE_GAME_NIM_THINKING", "0") == "1",
            timeout_seconds=float(os.getenv("INSIDE_GAME_NIM_TIMEOUT", "120")),
        )


class NimChatModel(AzureChatModel):
    """Reutiliza el adaptador Chat Completions, sus reintentos (429/5xx) y límites."""

    def _base_url(self):
        return NIM_ENDPOINT

    async def _headers(self):
        return {
            "Authorization": "Bearer " + self.settings.api_key,
            "User-Agent": "inside-game-sports-data-agent/0.0.0",
        }

    def _chat_body(self, instructions, messages, tools):
        body = super()._chat_body(instructions, messages, tools)
        body.pop("reasoning_effort")
        body["chat_template_kwargs"] = {"enable_thinking": self.settings.thinking}
        return body
