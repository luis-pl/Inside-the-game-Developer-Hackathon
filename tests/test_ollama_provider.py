"""Proveedor Ollama: transporte simulado, sin depender de un servidor local."""

import asyncio
import json

import httpx
import pytest

from inside_game.agents.insights_agent.runtime import model_label
from inside_game.providers.models import (
    ModelFailure,
    create_model,
    model_settings_from_env,
)
from inside_game.providers.ollama import (
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL,
    OllamaChatModel,
    OllamaModelSettings,
)

TOOL = {
    "type": "function",
    "name": "get_shots",
    "description": "Tiros",
    "parameters": {
        "type": "object",
        "properties": {"scope": {"$ref": "#/$defs/Scope"}},
        "$defs": {
            "Scope": {
                "type": "object",
                "properties": {"match_id": {"type": "integer"}},
            }
        },
    },
    "strict": False,
}


def completion(message, finish_reason="tool_calls"):
    return {
        "choices": [{"finish_reason": finish_reason, "message": message}],
        "usage": {"total_tokens": 42},
    }


def test_selected_explicitly_from_environment(monkeypatch):
    monkeypatch.setenv("INSIDE_GAME_MODEL_PROVIDER", "ollama")
    monkeypatch.delenv("INSIDE_GAME_OLLAMA_URL", raising=False)
    monkeypatch.delenv("INSIDE_GAME_OLLAMA_MODEL", raising=False)
    settings = model_settings_from_env()
    assert isinstance(settings, OllamaModelSettings)
    assert settings.endpoint == DEFAULT_ENDPOINT
    assert settings.deployment == DEFAULT_MODEL
    assert model_label() == DEFAULT_MODEL

    monkeypatch.setenv("INSIDE_GAME_OLLAMA_URL", "http://100.101.102.103:11434")
    monkeypatch.setenv("INSIDE_GAME_OLLAMA_MODEL", "qwen3:8b")
    settings = model_settings_from_env()
    assert settings.endpoint == "http://100.101.102.103:11434"
    assert model_label() == "qwen3:8b"
    assert isinstance(create_model(settings), OllamaChatModel)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://localhost:11434/v1",
        "http://127.0.0.1:11434",
        "http://[::1]:11434/v1/",
        "http://192.168.1.20:11434/v1",
        "https://100.64.0.7/v1",
    ],
)
def test_accepts_local_and_private_endpoints(endpoint):
    OllamaModelSettings(endpoint=endpoint)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://ollama.example.com:11434/v1",
        "http://8.8.8.8:11434/v1",
        "http://user:secret@127.0.0.1:11434/v1",
        "http://127.0.0.1:11434/v1?key=x",
        "http://127.0.0.1:11434/api",
        "ftp://127.0.0.1/v1",
    ],
)
def test_rejects_public_or_credentialed_endpoints(endpoint):
    with pytest.raises(ValueError):
        OllamaModelSettings(endpoint=endpoint)


@pytest.mark.parametrize(
    "changes",
    [
        {"deployment": ""},
        {"deployment": " qwen3:8b"},
        {"api": "responses"},
        {"max_output_tokens": 100},
        {"timeout_seconds": 0},
        {"timeout_seconds": 601},
    ],
)
def test_rejects_invalid_settings(changes):
    with pytest.raises(ValueError):
        OllamaModelSettings(**changes)


def test_chat_request_without_auth_or_reasoning_and_tool_call_parsing():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            json=completion(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "get_shots",
                                "arguments": '{"scope":{"match_id":900001}}',
                            },
                        }
                    ],
                }
            ),
        )

    async def scenario():
        async with OllamaChatModel(
            OllamaModelSettings(), transport=httpx.MockTransport(handler)
        ) as model:
            assert model.name == DEFAULT_MODEL
            return await model.respond(
                "rules", [{"role": "user", "content": "tiros"}], [TOOL]
            )

    turn = asyncio.run(scenario())
    request = seen[0]
    assert str(request.url) == DEFAULT_ENDPOINT + "/chat/completions"
    assert "authorization" not in request.headers
    assert "api-key" not in request.headers
    body = json.loads(request.content)
    assert body["model"] == DEFAULT_MODEL
    assert "reasoning_effort" not in body
    assert body["messages"][0] == {"role": "system", "content": "rules"}
    parameters = body["tools"][0]["function"]["parameters"]
    assert "$defs" not in parameters
    assert parameters["properties"]["scope"]["properties"]["match_id"] == {
        "type": "integer"
    }
    assert turn.total_tokens == 42
    assert turn.output[1] == {
        "type": "function_call",
        "call_id": "call_1",
        "name": "get_shots",
        "arguments": '{"scope":{"match_id":900001}}',
    }


def test_retries_one_transient_gpu_error_then_succeeds():
    attempts = []

    def handler(request):
        attempts.append(request)
        if len(attempts) == 1:
            return httpx.Response(500, json={"error": "CUDA error: unknown error"})
        return httpx.Response(
            200, json=completion({"role": "assistant", "content": "ok"}, "stop")
        )

    async def scenario():
        async with OllamaChatModel(
            OllamaModelSettings(), transport=httpx.MockTransport(handler)
        ) as model:
            return await model.respond("rules", [], [])

    turn = asyncio.run(scenario())
    assert len(attempts) == 2
    assert turn.output[0]["message"]["content"] == "ok"


@pytest.mark.parametrize(
    ("status", "code"),
    [(400, "MODEL_REQUEST_REJECTED"), (404, "MODEL_DEPLOYMENT_UNAVAILABLE")],
)
def test_errors_are_public_codes_without_server_body(status, code):
    def handler(request):
        return httpx.Response(status, json={"error": "detalle interno del servidor"})

    async def scenario():
        async with OllamaChatModel(
            OllamaModelSettings(), transport=httpx.MockTransport(handler)
        ) as model:
            await model.respond("rules", [], [])

    with pytest.raises(ModelFailure) as error:
        asyncio.run(scenario())
    assert error.value.code == code
    assert "interno" not in str(error.value)


def test_truncated_answer_is_incomplete():
    def handler(request):
        return httpx.Response(
            200, json=completion({"role": "assistant", "content": "..."}, "length")
        )

    async def scenario():
        async with OllamaChatModel(
            OllamaModelSettings(), transport=httpx.MockTransport(handler)
        ) as model:
            await model.respond("rules", [], [])

    with pytest.raises(ModelFailure, match="MODEL_INCOMPLETE_RESPONSE"):
        asyncio.run(scenario())
