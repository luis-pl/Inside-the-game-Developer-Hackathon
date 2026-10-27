"""Proveedor NVIDIA NIM: transporte simulado, sin llamar al servicio real."""

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
from inside_game.providers.nim import (
    DEFAULT_MODEL,
    NIM_ENDPOINT,
    NimChatModel,
    NimModelSettings,
)

KEY = "nvapi-test-secret-key"


def completion(message, finish_reason="tool_calls"):
    return {
        "choices": [{"finish_reason": finish_reason, "message": message}],
        "usage": {"total_tokens": 37},
    }


def test_selected_explicitly_from_environment(monkeypatch):
    monkeypatch.setenv("INSIDE_GAME_MODEL_PROVIDER", "nim")
    monkeypatch.setenv("INSIDE_GAME_NIM_API_KEY", KEY)
    monkeypatch.delenv("INSIDE_GAME_NIM_MODEL", raising=False)
    monkeypatch.delenv("INSIDE_GAME_NIM_THINKING", raising=False)
    settings = model_settings_from_env()
    assert isinstance(settings, NimModelSettings)
    assert settings.deployment == DEFAULT_MODEL and not settings.thinking
    assert KEY not in repr(settings)
    assert model_label() == DEFAULT_MODEL
    assert isinstance(create_model(settings), NimChatModel)

    monkeypatch.setenv("INSIDE_GAME_NIM_MODEL", "org/otro-modelo")
    monkeypatch.setenv("INSIDE_GAME_NIM_THINKING", "1")
    settings = model_settings_from_env()
    assert settings.deployment == "org/otro-modelo" and settings.thinking
    assert model_label() == "org/otro-modelo"


@pytest.mark.parametrize(
    "changes",
    [
        {"api_key": ""},
        {"api_key": " nvapi-x"},
        {"api_key": "nvapi\nx"},
        {"endpoint": "https://example.com/v1"},
        {"deployment": "sin-organizacion"},
        {"api": "responses"},
        {"max_output_tokens": 100},
        {"timeout_seconds": 0},
    ],
)
def test_rejects_invalid_settings(changes):
    with pytest.raises(ValueError):
        NimModelSettings(**{"api_key": KEY, **changes})


@pytest.mark.parametrize("thinking", [False, True])
def test_request_uses_fixed_endpoint_bearer_and_thinking_flag(thinking):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            json=completion(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "get_shots",
                                "arguments": '{"match_id":900001,"team_id":2}',
                            },
                        }
                    ],
                }
            ),
        )

    async def scenario():
        async with NimChatModel(
            NimModelSettings(api_key=KEY, thinking=thinking),
            transport=httpx.MockTransport(handler),
        ) as model:
            return await model.respond(
                "rules", [{"role": "user", "content": "goles"}], []
            )

    turn = asyncio.run(scenario())
    request = seen[0]
    assert str(request.url) == NIM_ENDPOINT + "/chat/completions"
    assert request.headers["Authorization"] == "Bearer " + KEY
    body = json.loads(request.content)
    assert body["model"] == DEFAULT_MODEL
    assert "reasoning_effort" not in body
    assert body["chat_template_kwargs"] == {"enable_thinking": thinking}
    assert turn.total_tokens == 37
    assert turn.output[1]["name"] == "get_shots"


def test_retries_one_rate_limit_then_succeeds():
    attempts = []

    def handler(request):
        attempts.append(request)
        if len(attempts) == 1:
            return httpx.Response(429, headers={"retry-after": "1"})
        return httpx.Response(
            200, json=completion({"role": "assistant", "content": "ok"}, "stop")
        )

    async def scenario():
        async with NimChatModel(
            NimModelSettings(api_key=KEY), transport=httpx.MockTransport(handler)
        ) as model:
            return await model.respond("rules", [], [])

    asyncio.run(scenario())
    assert len(attempts) == 2


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "MODEL_UNAUTHORIZED"),
        (402, "MODEL_BILLING_REQUIRED"),
        (404, "MODEL_DEPLOYMENT_UNAVAILABLE"),
    ],
)
def test_errors_are_public_codes_without_server_body(status, code):
    def handler(request):
        return httpx.Response(status, json={"error": "detalle interno " + KEY})

    async def scenario():
        async with NimChatModel(
            NimModelSettings(api_key=KEY), transport=httpx.MockTransport(handler)
        ) as model:
            await model.respond("rules", [], [])

    with pytest.raises(ModelFailure) as error:
        asyncio.run(scenario())
    assert error.value.code == code
    assert KEY not in str(error.value)
