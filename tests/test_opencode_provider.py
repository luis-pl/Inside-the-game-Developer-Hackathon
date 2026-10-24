"""Conector Console/Zen: transporte simulado, sin gastar crédito ni usar Go."""

import asyncio
import json
import sqlite3
import time
from uuid import uuid4

import httpx
import pytest

from inside_game.providers.models import (
    AzureModelSettings,
    ModelFailure,
    create_model,
    model_settings_from_env,
)
from inside_game.providers.opencode import (
    CONSOLE_ENDPOINT,
    GO_ENDPOINT,
    OpenCodeChatModel,
    OpenCodeModelSettings,
    OpenCodeResponsesModel,
    read_cli_session,
)


def cli_database(tmp_path, *, server="https://console.opencode.ai", expired=False):
    path = tmp_path / "opencode.db"
    with sqlite3.connect(path) as db:
        db.executescript(
            "CREATE TABLE account(id TEXT,url TEXT,access_token TEXT,token_expiry INTEGER);"
            "CREATE TABLE account_state(id INTEGER,active_account_id TEXT,active_org_id TEXT);"
        )
        db.execute(
            "INSERT INTO account VALUES(?,?,?,?)",
            (
                "selected",
                server,
                "SESSION-SECRET",
                int(time.time() * 1000) + (-1 if expired else 300000),
            ),
        )
        db.execute("INSERT INTO account_state VALUES(1,'selected','wrk_test')")
    return path


@pytest.mark.parametrize("paid", [False, True])
def test_cli_go_session_checks_current_free_price_before_inference(tmp_path, paid):
    path = cli_database(tmp_path)
    seen = []

    def handler(request):
        seen.append((request.method, str(request.url)))
        assert request.headers["Authorization"] == "Bearer SESSION-SECRET"
        assert request.headers["User-Agent"] == "inside-game-sports-data-agent/0.0.0"
        if request.method == "GET":
            assert request.headers["x-org-id"] == "wrk_test"
            return httpx.Response(
                200,
                json={
                    "config": {
                        "provider": {
                            "opencode-go": {
                                "api": GO_ENDPOINT,
                                "models": {
                                    "beam-free": {
                                        "cost": {"input": int(paid), "output": 0}
                                    }
                                },
                            }
                        }
                    }
                },
            )
        assert str(request.url) == GO_ENDPOINT + "/chat/completions"
        assert request.headers["x-opencode-org-id"] == "wrk_test"
        assert request.headers["x-opencode-session"] == conversation
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "ok"},
                    }
                ]
            },
        )

    conversation = str(uuid4())

    async def scenario():
        settings = OpenCodeModelSettings(
            provider="opencode-go",
            endpoint=GO_ENDPOINT,
            deployment="beam-free",
            api="chat_completions",
            auth_mode="cli_session",
            cli_db=str(path),
            free_only=True,
        )
        assert "SESSION-SECRET" not in repr(settings)
        async with OpenCodeChatModel(
            settings, transport=httpx.MockTransport(handler)
        ) as model:
            args = (
                "sports data",
                [{"role": "user", "content": json.dumps({"request_id": conversation})}],
                [],
            )
            if paid:
                with pytest.raises(ModelFailure, match="MODEL_FREE_STATUS_UNVERIFIED"):
                    await model.respond(*args)
            else:
                await model.respond(*args)
                with sqlite3.connect(path) as db:
                    db.execute("UPDATE account SET token_expiry=0")
                with pytest.raises(ModelFailure, match="MODEL_CLI_SESSION_EXPIRED"):
                    await model.respond(*args)

    asyncio.run(scenario())
    assert [method for method, _ in seen] == (["GET"] if paid else ["GET", "POST"])


def test_cli_auth_is_explicit_and_rejects_untrusted_account_servers(
    tmp_path, monkeypatch
):
    path = cli_database(tmp_path, server="https://attacker.test")
    with pytest.raises(ModelFailure, match="MODEL_AUTHENTICATION_FAILED"):
        read_cli_session(str(path))
    monkeypatch.setenv("INSIDE_GAME_OPENCODE_AUTH_MODE", "cli_session")
    monkeypatch.setenv("INSIDE_GAME_OPENCODE_CLI_DB", str(path))
    monkeypatch.setenv("INSIDE_GAME_OPENCODE_MODEL", "beam-free")
    monkeypatch.setenv("INSIDE_GAME_OPENCODE_API", "chat_completions")
    monkeypatch.setenv("INSIDE_GAME_OPENCODE_FREE_ONLY", "1")
    assert OpenCodeModelSettings.from_env("opencode-go").api_key == ""
    with pytest.raises(ValueError):
        OpenCodeModelSettings.from_env("opencode")
    with pytest.raises(ValueError):
        OpenCodeModelSettings(api_key="key", deployment="beam-free")


def test_console_credential_does_not_implicitly_use_go(monkeypatch, tmp_path):
    path = tmp_path / "auth.json"
    path.write_text(
        json.dumps({"opencode-go": {"type": "api", "key": "GO-KEY"}}),
        encoding="utf-8",
    )
    monkeypatch.delenv("INSIDE_GAME_OPENCODE_API_KEY", raising=False)
    monkeypatch.setenv("INSIDE_GAME_OPENCODE_AUTH_FILE", str(path))
    with pytest.raises(ValueError, match="API key for the selected plan"):
        OpenCodeModelSettings.from_env()


def test_selects_only_console_entry_and_hides_secret(monkeypatch, tmp_path):
    path = tmp_path / "auth.json"
    path.write_text(
        json.dumps(
            {
                "opencode": {"type": "api", "key": "CONSOLE-KEY"},
                "opencode-go": {"type": "api", "key": "GO-KEY"},
                "azure": {"type": "api", "key": "AZURE-KEY"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("INSIDE_GAME_OPENCODE_API_KEY", raising=False)
    monkeypatch.setenv("INSIDE_GAME_OPENCODE_AUTH_FILE", str(path))
    settings = OpenCodeModelSettings.from_env()
    assert settings.api_key == "CONSOLE-KEY"
    assert "CONSOLE-KEY" not in repr(settings)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://opencode.ai/inference/openai/v1",
        "https://opencode.ai.attacker.test/inference/openai/v1",
        "https://user:secret@opencode.ai/inference/openai/v1",
        CONSOLE_ENDPOINT + "?key=secret",
        "https://opencode.ai/inference/go/openai/v1",
    ],
)
def test_key_cannot_be_sent_to_other_destinations(endpoint):
    with pytest.raises(ValueError, match="official OpenCode endpoint"):
        OpenCodeModelSettings(endpoint=endpoint, api_key="test-key")


def test_azure_destination_restriction_still_applies():
    with pytest.raises(ValueError):
        AzureModelSettings(CONSOLE_ENDPOINT)


def test_unknown_provider_does_not_fall_back(monkeypatch):
    monkeypatch.setenv("INSIDE_GAME_MODEL_PROVIDER", "unknown-provider")
    with pytest.raises(ValueError, match="Unsupported model provider"):
        model_settings_from_env()


def test_factory_selects_console_explicitly(monkeypatch):
    monkeypatch.setenv("INSIDE_GAME_MODEL_PROVIDER", "opencode")
    monkeypatch.setenv("INSIDE_GAME_OPENCODE_API_KEY", "console-test")
    settings = model_settings_from_env()
    assert isinstance(settings, OpenCodeModelSettings)

    async def scenario():
        async with create_model(settings) as model:
            assert isinstance(model, OpenCodeResponsesModel)
            assert model.settings.endpoint == CONSOLE_ENDPOINT

    asyncio.run(scenario())


def test_responses_bearer_and_reasoning_are_preserved():
    seen = []
    reasoning = {"type": "reasoning", "encrypted_content": "opaque", "summary": []}
    call = {
        "type": "function_call",
        "call_id": "call-shots",
        "name": "get_shots",
        "arguments": '{"match_id":900001}',
    }

    def handler(request):
        assert str(request.url) == CONSOLE_ENDPOINT + "/responses"
        assert request.headers["Authorization"] == "Bearer console-test"
        assert "api-key" not in request.headers
        assert request.headers["User-Agent"] == "inside-game-sports-data-agent/0.0.0"
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [reasoning, call],
                "usage": {"total_tokens": 120},
            },
        )

    async def scenario():
        async with OpenCodeResponsesModel(
            OpenCodeModelSettings(api_key="console-test"),
            transport=httpx.MockTransport(handler),
        ) as model:
            first = await model.respond(
                "rules", [{"role": "user", "content": "shots"}], []
            )
            assert first.total_tokens == 120
            await model.respond(
                "rules",
                first.output
                + [
                    {
                        "type": "function_call_output",
                        "call_id": "call-shots",
                        "output": '{"data":[]}',
                    }
                ],
                [],
            )

    asyncio.run(scenario())
    assert seen[1]["input"][0] == reasoning
    assert seen[1]["input"][2]["call_id"] == "call-shots"
    assert seen[0]["store"] is False


def test_chat_completions_preserves_calls():
    def handler(request):
        assert str(request.url) == CONSOLE_ENDPOINT + "/chat/completions"
        assert request.headers["Authorization"] == "Bearer console-test"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "get_shots",
                                        "arguments": "{}",
                                    },
                                }
                            ],
                        },
                    }
                ],
                "usage": {"total_tokens": 50},
            },
        )

    async def scenario():
        settings = OpenCodeModelSettings(
            api_key="console-test", deployment="kimi-k3", api="chat_completions"
        )
        async with OpenCodeChatModel(
            settings, transport=httpx.MockTransport(handler)
        ) as model:
            turn = await model.respond("rules", [], [])
            assert turn.output[1]["call_id"] == "call-1"

    asyncio.run(scenario())


def test_missing_credit_stops_without_fallback_or_secret_leak():
    attempts = []

    def handler(request):
        attempts.append(request)
        return httpx.Response(402, text="console-test SECRET PROVIDER BODY")

    async def scenario():
        async with OpenCodeResponsesModel(
            OpenCodeModelSettings(api_key="console-test"),
            transport=httpx.MockTransport(handler),
        ) as model:
            with pytest.raises(ModelFailure, match="MODEL_BILLING_REQUIRED") as error:
                await model.respond("rules", [], [])
            assert "console-test" not in str(error.value)

    asyncio.run(scenario())
    assert len(attempts) == 1


def test_go_is_explicit_and_preserves_independent_conversation_sessions(
    monkeypatch, tmp_path
):
    path = tmp_path / "auth.json"
    path.write_text(
        json.dumps(
            {
                "opencode": {"type": "api", "key": "CONSOLE-KEY"},
                "opencode-go": {"type": "api", "key": "GO-KEY"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("INSIDE_GAME_OPENCODE_API_KEY", raising=False)
    monkeypatch.setenv("INSIDE_GAME_MODEL_PROVIDER", "opencode-go")
    monkeypatch.setenv("INSIDE_GAME_OPENCODE_AUTH_FILE", str(path))
    settings = model_settings_from_env()
    assert settings.api_key == "GO-KEY" and settings.endpoint == GO_ENDPOINT
    seen = []

    async def handler(request):
        await asyncio.sleep(0)
        assert str(request.url) == GO_ENDPOINT + "/responses"
        assert request.headers["Authorization"] == "Bearer GO-KEY"
        assert request.headers["User-Agent"] == "inside-game-sports-data-agent/0.0.0"
        body = json.loads(request.content)
        expected = json.loads(body["input"][0]["content"])["request_id"]
        assert request.headers["x-opencode-session"] == expected
        seen.append(expected)
        return httpx.Response(200, json={"status": "completed", "output": []})

    async def scenario():
        async with OpenCodeResponsesModel(
            settings, transport=httpx.MockTransport(handler)
        ) as model:

            async def conversation(identifier):
                messages = [
                    {"role": "user", "content": json.dumps({"request_id": identifier})}
                ]
                await model.respond("sports data", messages, [])
                await model.respond("sports data", messages, [])

            await asyncio.gather(conversation(str(uuid4())), conversation(str(uuid4())))

    asyncio.run(scenario())
    assert len(seen) == 4 and len(set(seen)) == 2


@pytest.mark.parametrize(
    "status,code", [(401, "MODEL_UNAUTHORIZED"), (402, "MODEL_BILLING_REQUIRED")]
)
def test_go_failure_never_switches_to_console(status, code):
    attempted_urls = []

    def handler(request):
        attempted_urls.append(str(request.url))
        return httpx.Response(status, text="GO-KEY SECRET")

    async def scenario():
        settings = OpenCodeModelSettings(
            provider="opencode-go", endpoint=GO_ENDPOINT, api_key="GO-KEY"
        )
        async with OpenCodeResponsesModel(
            settings, transport=httpx.MockTransport(handler)
        ) as model:
            with pytest.raises(ModelFailure, match=code):
                await model.respond(
                    "sports data",
                    [
                        {
                            "role": "user",
                            "content": json.dumps({"request_id": str(uuid4())}),
                        }
                    ],
                    [],
                )

    asyncio.run(scenario())
    assert attempted_urls == [GO_ENDPOINT + "/responses"]


def test_go_missing_conversation_id_fails_before_network():
    async def scenario():
        settings = OpenCodeModelSettings(
            provider="opencode-go", endpoint=GO_ENDPOINT, api_key="GO-KEY"
        )

        def forbidden_request(request):
            raise AssertionError("Do not send Go requests without a conversation ID")

        async with OpenCodeResponsesModel(
            settings, transport=httpx.MockTransport(forbidden_request)
        ) as model:
            with pytest.raises(ModelFailure, match="MODEL_SESSION_REQUIRED"):
                await model.respond(
                    "sports data", [{"role": "user", "content": "hi"}], []
                )

    asyncio.run(scenario())
