import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from mcp import Client

from inside_game.api import create_app
from inside_game.mcp_server import (
    DESCRIPTIONS,
    MAX_RESPONSE,
    ApiBridge,
    McpSettings,
    create_http_app,
    create_server,
    tool_catalog,
)
from inside_game.service import OPERATIONS
from inside_game.settings import Settings

TOKEN = "test-only-credential-32-characters-long"


def error_code(result):
    assert result.is_error
    return json.loads(result.content[0].text)["error"]["code"]


def test_wire_discovery_and_azure_shaped_results(repository):
    async def run():
        api = create_app(Settings(api_key=TOKEN, local_access=False), repository)
        server = create_server(McpSettings(api_key=TOKEN), httpx.ASGITransport(app=api))
        async with Client(server) as client:
            tools = (await client.list_tools()).tools
            assert len(tools) == 34
            assert {t.name for t in tools} == set(OPERATIONS) == set(DESCRIPTIONS)
            for tool in tools:
                assert tool.input_schema == OPERATIONS[tool.name].model_json_schema()
                assert tool.input_schema["additionalProperties"] is False
                assert tool.output_schema
                assert tool.annotations.read_only_hint
                assert not tool.annotations.destructive_hint
            result = await client.call_tool(
                "get_shots",
                {"match_id": 900001, "view": "summary", "outcome": "on_target"},
            )
            assert not result.is_error
            payload = result.structured_content
            assert payload["data"]["summary"]["shots_on_target"] == 2
            assert payload["provenance"]["is_synthetic"] is True
            assert payload["warnings"] and payload["coordinates"]
            assert json.loads(result.content[0].text) == payload
            frame = await client.call_tool(
                "get_tracking_frame", {"match_id": 900001, "period": 1, "time_ms": 1000}
            )
            assert not frame.is_error
            invalid = await client.call_tool(
                "get_shots", {"match_id": 900001, "sql": "SECRET SQL"}
            )
            assert error_code(invalid) == "INVALID_ARGUMENT"
            assert "SECRET SQL" not in invalid.content[0].text
            unknown = await client.call_tool("execute_query", {"sql": "SELECT 1"})
            assert error_code(unknown) == "UNREGISTERED_OPERATION"

    asyncio.run(run())


@pytest.mark.parametrize(
    "arguments",
    [
        {"match_id": True},
        {"match_id": "900001 OR 1=1"},
        {"match_id": 900001, "scope": {"kind": "match", "sql": "SECRET"}},
        {"match_id": 900001, "limit": 201},
        {"match_id": 900001, "outcome": "invented"},
    ],
)
def test_invalid_inputs_never_reach_http(arguments):
    def unexpected(request):
        pytest.fail("Invalid input reached the API")

    bridge = ApiBridge(transport=httpx.MockTransport(unexpected))
    assert (
        error_code(asyncio.run(bridge.call("get_shots", arguments)))
        == "INVALID_ARGUMENT"
    )


@pytest.mark.parametrize(
    "status,expected",
    [
        (401, "UNAUTHORIZED"),
        (403, "FORBIDDEN"),
        (404, "NOT_FOUND"),
        (413, "RESPONSE_TOO_LARGE"),
        (422, "INVALID_ARGUMENT"),
        (429, "RATE_LIMITED"),
        (500, "API_UNAVAILABLE"),
        (503, "API_UNAVAILABLE"),
        (302, "API_UNAVAILABLE"),
    ],
)
def test_upstream_failures_are_sanitized(status, expected):
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(
            status,
            text="SECRET SERVER TOKEN",
            headers={"Location": "https://evil.invalid"},
        )

    bridge = ApiBridge(McpSettings(api_key=TOKEN), httpx.MockTransport(respond))
    result = asyncio.run(bridge.call("get_shots", {"match_id": 900001}))
    assert error_code(result) == expected
    assert "SECRET" not in result.content[0].text
    assert len(seen) == 1
    assert seen[0].url.path == "/api/operations/get_shots"
    assert seen[0].headers["Authorization"] == "Bearer " + TOKEN


def test_transport_failure_is_recoverable():
    def fail(request):
        raise httpx.ConnectError("SECRET HOST", request=request)

    result = asyncio.run(
        ApiBridge(transport=httpx.MockTransport(fail)).call("describe_dataset", {})
    )
    assert error_code(result) == "API_UNAVAILABLE"
    assert "SECRET" not in result.content[0].text


@pytest.mark.parametrize(
    "body",
    [b"not-json", b"{}", b"x" * (MAX_RESPONSE + 1)],
    ids=["invalid-json", "invalid-contract", "too-large"],
)
def test_invalid_and_oversized_responses(body):
    bridge = ApiBridge(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body))
    )
    result = asyncio.run(bridge.call("describe_dataset", {}))
    assert error_code(result) == (
        "RESPONSE_TOO_LARGE" if len(body) > MAX_RESPONSE else "INVALID_API_RESPONSE"
    )


def test_rate_and_concurrency_limits():
    bridge = ApiBridge()
    bridge.active = 4
    assert error_code(asyncio.run(bridge.call("describe_dataset", {}))) == "BUSY"
    import time

    bridge.requests.extend([time.monotonic()] * 120)
    assert (
        error_code(asyncio.run(bridge.call("describe_dataset", {}))) == "RATE_LIMITED"
    )


@pytest.mark.parametrize(
    "url,key",
    [
        ("http://example.com", TOKEN),
        ("https://example.com", ""),
        ("http://user:secret@127.0.0.1:8000", ""),
        ("http://127.0.0.1:8000/?token=x", ""),
        ("file:///tmp/db", ""),
    ],
)
def test_api_destination_is_server_owned_and_validated(url, key):
    with pytest.raises(ValueError):
        McpSettings(api_url=url, api_key=key)


def test_http_boundary_and_dns_rebinding():
    app = create_http_app(create_server())
    with TestClient(
        app, base_url="http://127.0.0.1:8001", client=("127.0.0.1", 9999)
    ) as client:
        headers = {"Accept": "application/json, text/event-stream"}
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        }
        assert client.post("/mcp", json=body, headers=headers).status_code == 200
        assert (
            client.post(
                "/mcp", json=body, headers={**headers, "Host": "evil.example"}
            ).status_code
            == 421
        )
        assert (
            client.post(
                "/mcp", json=body, headers={**headers, "Origin": "https://evil.example"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/mcp",
                content=b"x" * 65537,
                headers={**headers, "Content-Type": "application/json"},
            ).status_code
            == 413
        )
    with TestClient(
        create_http_app(create_server()),
        base_url="http://127.0.0.1:8001",
        client=("10.0.0.2", 9999),
    ) as client:
        assert client.post("/mcp", json=body, headers=headers).status_code == 403


def test_descriptions_cover_registry():
    assert len(tool_catalog()) == len(DESCRIPTIONS) == len(OPERATIONS)
