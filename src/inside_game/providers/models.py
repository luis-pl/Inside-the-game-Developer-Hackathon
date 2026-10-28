"""Adaptadores Azure Responses y Chat Completions; sin acceso a herramientas.

El proveedor sólo propone function_calls. El ejecutor del agente valida y llama
al MCP. Se conserva response.output completo, incluidos elementos de razonamiento,
para reenviarlo con function_call_output en el siguiente turno (store=false).
"""

import asyncio
import os
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlsplit

import httpx


class ModelFailure(Exception):
    """Código público seguro: jamás devolver el cuerpo HTTP ni tokens de Azure."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ModelTurn:
    output: list[dict]
    total_tokens: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None


def token_usage(payload):
    usage = payload.get("usage") or {}

    def count(value):
        return value if type(value) is int and value >= 0 else None

    details = (
        usage.get("input_tokens_details", usage.get("prompt_tokens_details")) or {}
    )
    return {
        "input_tokens": count(usage.get("input_tokens", usage.get("prompt_tokens"))),
        "output_tokens": count(
            usage.get("output_tokens", usage.get("completion_tokens"))
        ),
        "cached_tokens": count(details.get("cached_tokens")),
    }


class ModelProvider(Protocol):
    name: str

    async def respond(
        self, instructions: str, messages: list, tools: list
    ) -> ModelTurn: ...


@dataclass(frozen=True)
class AzureModelSettings:
    endpoint: str
    deployment: str = "gpt-6-luna"
    reasoning_effort: str = "medium"
    auth: str = "default"
    api_key: str = field(default="", repr=False)
    max_output_tokens: int = 4096
    timeout_seconds: float = 60
    api: str = "responses"

    def __post_init__(self):
        url = urlsplit(self.endpoint)
        if (
            url.scheme != "https"
            or not url.hostname
            or not url.hostname.endswith(
                (".openai.azure.com", ".services.ai.azure.com")
            )
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.port not in (None, 443)
            or url.path not in ("", "/", "/openai/v1", "/openai/v1/")
        ):
            raise ValueError(
                "Configure an Azure OpenAI HTTPS endpoint without credentials"
            )
        if self.auth not in {"default", "azure_cli", "managed_identity", "api_key"}:
            raise ValueError("Unsupported Azure model authentication")
        if self.api not in {"responses", "chat_completions"}:
            raise ValueError("Unsupported model API")
        if self.auth == "api_key" and not self.api_key:
            raise ValueError("Azure OpenAI API key is missing")
        if self.reasoning_effort not in {"none", "low", "medium", "high"}:
            raise ValueError("Unsupported reasoning effort")
        if not self.deployment or not 256 <= self.max_output_tokens <= 8192:
            raise ValueError("Invalid model deployment or output budget")

    @classmethod
    def from_env(cls):
        return cls(
            endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
            deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-6-luna"),
            reasoning_effort=os.getenv("INSIDE_GAME_REASONING_EFFORT", "medium"),
            auth=os.getenv("INSIDE_GAME_MODEL_AUTH", "default"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
            api=os.getenv("INSIDE_GAME_MODEL_API", "responses"),
        )


class AzureResponsesModel:
    def __init__(self, settings: AzureModelSettings, *, transport=None):
        self.settings = settings
        self.name = settings.deployment
        self._http = httpx.AsyncClient(
            timeout=settings.timeout_seconds,
            trust_env=False,
            follow_redirects=False,
            transport=transport,
        )
        self._credential = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._http.aclose()
        if self._credential:
            await asyncio.to_thread(self._credential.close)

    async def _headers(self):
        if self.settings.auth == "api_key":
            return {"api-key": self.settings.api_key}
        # Importación perezosa: las pruebas de contrato no necesitan Azure.
        from azure.core.exceptions import ClientAuthenticationError
        from azure.identity import (
            AzureCliCredential,
            DefaultAzureCredential,
            ManagedIdentityCredential,
        )

        if self._credential is None:
            if self.settings.auth == "azure_cli":
                self._credential = AzureCliCredential(process_timeout=30)
            elif self.settings.auth == "managed_identity":
                self._credential = ManagedIdentityCredential(
                    client_id=os.getenv("AZURE_CLIENT_ID") or None
                )
            else:
                self._credential = DefaultAzureCredential(
                    exclude_interactive_browser_credential=True
                )
        try:
            token = await asyncio.to_thread(
                self._credential.get_token,
                "https://cognitiveservices.azure.com/.default",
            )
        except ClientAuthenticationError:
            raise ModelFailure("MODEL_AUTHENTICATION_FAILED") from None
        return {"Authorization": "Bearer " + token.token}

    async def respond(self, instructions, messages, tools):
        body = {
            "model": self.name,
            "instructions": instructions,
            "input": messages,
            "tools": tools,
            "tool_choice": "required",
            "parallel_tool_calls": False,
            "reasoning": {"effort": self.settings.reasoning_effort},
            "max_output_tokens": self.settings.max_output_tokens,
            "store": False,
            "include": ["reasoning.encrypted_content"],
        }
        payload = await self._post("responses", body)
        if payload.get("status") != "completed" or not isinstance(
            payload.get("output"), list
        ):
            raise ModelFailure("MODEL_INCOMPLETE_RESPONSE")
        return ModelTurn(
            payload["output"],
            int((payload.get("usage") or {}).get("total_tokens", 0)),
            **token_usage(payload),
        )

    def _base_url(self):
        endpoint = self.settings.endpoint.rstrip("/")
        if not endpoint.endswith("/openai/v1"):
            endpoint += "/openai/v1"
        return endpoint

    async def _post(self, path, body):
        endpoint = self._base_url()
        # Un único reintento transitorio. No reenviar errores/cuerpos al modelo.
        for attempt in range(2):
            try:
                async with self._http.stream(
                    "POST",
                    endpoint + "/" + path,
                    json=body,
                    headers=await self._headers(),
                ) as response:
                    if (
                        response.status_code in (429, 500, 502, 503, 504)
                        and attempt == 0
                    ):
                        try:
                            wait = float(response.headers.get("retry-after", "1"))
                        except ValueError:
                            wait = 1
                        await asyncio.sleep(min(max(wait, 1), 60))
                        continue
                    if response.status_code != 200:
                        code = {
                            400: "MODEL_REQUEST_REJECTED",
                            402: "MODEL_BILLING_REQUIRED",
                            404: "MODEL_DEPLOYMENT_UNAVAILABLE",
                            401: "MODEL_UNAUTHORIZED",
                            403: "MODEL_UNAUTHORIZED",
                            429: "MODEL_RATE_LIMITED",
                        }.get(response.status_code, "MODEL_UNAVAILABLE")
                        raise ModelFailure(code)
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 1024 * 1024:
                            raise ModelFailure("MODEL_RESPONSE_TOO_LARGE")
                import json

                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ModelFailure("MODEL_INVALID_RESPONSE")
                return payload
            except httpx.TransportError:
                if attempt == 0:
                    await asyncio.sleep(1)
                    continue
                raise ModelFailure("MODEL_UNAVAILABLE") from None
            except (ValueError, TypeError):
                raise ModelFailure("MODEL_INVALID_RESPONSE") from None
        raise ModelFailure("MODEL_UNAVAILABLE")


def chat_messages(instructions, messages):
    """Adapta el historial del ejecutor sin perder llamadas, IDs ni contexto."""
    result = [{"role": "system", "content": instructions}]
    represented = set()
    for item in messages:
        if item.get("type") == "chat_message":
            message = item["message"]
            result.append(message)
            represented.update(t["id"] for t in message.get("tool_calls", []))
        elif item.get("type") == "function_call":
            if item["call_id"] not in represented:
                result.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": item["call_id"],
                                "type": "function",
                                "function": {
                                    "name": item["name"],
                                    "arguments": item["arguments"],
                                },
                            }
                        ],
                    }
                )
        elif item.get("type") == "function_call_output":
            result.append(
                {
                    "role": "tool",
                    "tool_call_id": item["call_id"],
                    "content": item["output"],
                }
            )
        elif item.get("role") in {"user", "assistant"}:
            result.append(item)
    return result


def inline_tool_schema(schema):
    """Expande refs locales de Pydantic para el renderizador GPT-OSS de Azure.

    Las enumeraciones numéricas se describen como texto porque el renderizador
    de este modelo las rechaza. La validación efectiva conserva todos los enums
    en el modelo Pydantic original del ejecutor, MCP y API.
    """

    def expand(value, depth=0):
        if depth > 32:
            raise ValueError("Recursive tool schema is not supported")
        if isinstance(value, list):
            return [expand(v, depth + 1) for v in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            pointer = value["$ref"]
            if not pointer.startswith("#/"):
                raise ValueError("Only local schema references are supported")
            target = schema
            for part in pointer[2:].split("/"):
                target = target[part.replace("~1", "/").replace("~0", "~")]
            return expand(
                {**target, **{k: v for k, v in value.items() if k != "$ref"}}, depth + 1
            )
        result = {
            "anyOf" if k == "oneOf" else k: expand(v, depth + 1)
            for k, v in value.items()
            if k not in {"$defs", "discriminator"}
        }
        enum = result.get("enum")
        if enum and any(not isinstance(v, str) for v in enum):
            result.pop("enum")
            result["description"] = (
                result.get("description", "") + " Valores permitidos: " + str(enum)
            ).strip()
        return result

    return expand(schema)


class AzureChatModel(AzureResponsesModel):
    """Chat Completions de Foundry, probado con GPT-OSS y DeepSeek V4 Flash.

    Conserva reasoning_content entre llamadas de herramientas. Las adaptaciones
    de esquema por compatibilidad GPT-OSS no sustituyen validación del ejecutor.
    """

    def _chat_body(self, instructions, messages, tools):
        return {
            "model": self.name,
            "messages": chat_messages(instructions, messages),
            "tools": [
                {
                    "type": "function",
                    "function": {
                        k: inline_tool_schema(v) if k == "parameters" else v
                        for k, v in tool.items()
                        if k not in {"type", "strict"}
                    },
                }
                for tool in tools
            ],
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "reasoning_effort": self.settings.reasoning_effort,
            "max_tokens": self.settings.max_output_tokens,
        }

    async def respond(self, instructions, messages, tools):
        payload = await self._post(
            "chat/completions", self._chat_body(instructions, messages, tools)
        )
        try:
            choice = payload["choices"][0]
            if choice["finish_reason"] not in {"tool_calls", "stop"}:
                raise ModelFailure("MODEL_INCOMPLETE_RESPONSE")
            raw = choice["message"]
            message = {
                k: v
                for k, v in raw.items()
                if k in {"role", "content", "tool_calls", "reasoning_content"}
            }
            output = [{"type": "chat_message", "message": message}]
            for call in raw.get("tool_calls", []):
                output.append(
                    {
                        "type": "function_call",
                        "call_id": call["id"],
                        "name": call["function"]["name"],
                        "arguments": call["function"]["arguments"],
                    }
                )
            return ModelTurn(
                output,
                int((payload.get("usage") or {}).get("total_tokens", 0)),
                **token_usage(payload),
            )
        except (KeyError, IndexError, TypeError, ValueError):
            raise ModelFailure("MODEL_INVALID_RESPONSE") from None


def model_settings_from_env():
    """Selección de proveedor exclusiva de configuración, nunca del prompt."""
    provider = os.getenv("INSIDE_GAME_MODEL_PROVIDER", "azure")
    if provider in {"opencode", "opencode-go"}:
        from inside_game.providers.opencode import OpenCodeModelSettings

        return OpenCodeModelSettings.from_env(provider=provider)
    if provider == "ollama":
        from inside_game.providers.ollama import OllamaModelSettings

        return OllamaModelSettings.from_env()
    if provider == "nim":
        from inside_game.providers.nim import NimModelSettings

        return NimModelSettings.from_env()
    if provider != "azure":
        raise ValueError("Unsupported model provider")
    return AzureModelSettings.from_env()


def create_model(settings=None):
    settings = settings or model_settings_from_env()
    if getattr(settings, "provider", "azure") == "ollama":
        from inside_game.providers.ollama import OllamaChatModel

        return OllamaChatModel(settings)
    if getattr(settings, "provider", "azure") == "nim":
        from inside_game.providers.nim import NimChatModel

        return NimChatModel(settings)
    if getattr(settings, "provider", "azure") in {"opencode", "opencode-go"}:
        from inside_game.providers.opencode import (
            OpenCodeChatModel,
            OpenCodeResponsesModel,
        )

        return (
            OpenCodeChatModel(settings)
            if settings.api == "chat_completions"
            else OpenCodeResponsesModel(settings)
        )
    return (
        AzureChatModel(settings)
        if settings.api == "chat_completions"
        else AzureResponsesModel(settings)
    )
