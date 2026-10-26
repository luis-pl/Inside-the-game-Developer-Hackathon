"""Ollama local mediante su API compatible con Chat Completions; sin coste.

El destino debe ser este equipo o una dirección privada (LAN o Tailscale): el
servidor de Ollama no tiene autenticación. El contexto no se elige por petición
en la API compatible; se configura en el servidor con OLLAMA_CONTEXT_LENGTH.
Este cliente no descarga modelos, no cambia la configuración de Ollama y no hace
fallback a otro proveedor.
"""

import ipaddress
import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from inside_game.providers.models import AzureChatModel

DEFAULT_ENDPOINT = "http://127.0.0.1:11434/v1"
DEFAULT_MODEL = "qwen3:30b-a3b-instruct-2507-q4_K_M"
# Tailscale asigna direcciones del rango CGNAT, que ipaddress no marca privado.
TAILSCALE = ipaddress.ip_network("100.64.0.0/10")


def _private_host(host):
    if host == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private or address in TAILSCALE


@dataclass(frozen=True)
class OllamaModelSettings:
    endpoint: str = DEFAULT_ENDPOINT
    deployment: str = DEFAULT_MODEL
    api: str = "chat_completions"
    max_output_tokens: int = 4096
    # La primera petición carga el modelo y procesa ~20k tokens de herramientas.
    timeout_seconds: float = 300
    provider: str = "ollama"
    # Compatibilidad con el adaptador compartido; no se envía a Ollama.
    reasoning_effort: str = "none"

    def __post_init__(self):
        url = urlsplit(self.endpoint)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or not _private_host(url.hostname)
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in ("", "/", "/v1", "/v1/")
        ):
            raise ValueError(
                "Configure a local or private Ollama endpoint without credentials"
            )
        if (
            not isinstance(self.deployment, str)
            or not self.deployment
            or self.deployment.strip() != self.deployment
        ):
            raise ValueError("Configure the Ollama model name")
        if self.api != "chat_completions":
            raise ValueError("Ollama only supports the chat_completions API")
        if not 256 <= self.max_output_tokens <= 8192:
            raise ValueError("Invalid model output budget")
        if not 0 < self.timeout_seconds <= 600:
            raise ValueError("Invalid model timeout")

    @classmethod
    def from_env(cls):
        return cls(
            endpoint=os.getenv("INSIDE_GAME_OLLAMA_URL", DEFAULT_ENDPOINT),
            deployment=os.getenv("INSIDE_GAME_OLLAMA_MODEL", DEFAULT_MODEL),
            timeout_seconds=float(os.getenv("INSIDE_GAME_OLLAMA_TIMEOUT", "300")),
        )


class OllamaChatModel(AzureChatModel):
    """Reutiliza el adaptador Chat Completions, sus reintentos y límites."""

    def _base_url(self):
        endpoint = self.settings.endpoint.rstrip("/")
        return endpoint if endpoint.endswith("/v1") else endpoint + "/v1"

    async def _headers(self):
        return {"User-Agent": "inside-game-sports-data-agent/0.0.0"}

    def _chat_body(self, instructions, messages, tools):
        body = super()._chat_body(instructions, messages, tools)
        # El razonamiento depende del modelo elegido en Ollama. No se pide aquí:
        # en un modelo híbrido multiplicaría la latencia de cada turno.
        body.pop("reasoning_effort")
        return body
