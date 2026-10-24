"""QA del ejecutor: MCP real en memoria + modelo programado sin coste Azure.

Estas pruebas validan ejecución y preservación, no comprensión lingüística de
Luna. La evaluación real del modelo está separada en scripts/verify_data_agent.py.
"""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from mcp import Client
from mcp.types import CallToolResult, TextContent

from inside_game.agents.contracts import DataRequest
from inside_game.agents.data_agent import AgentLimits, DataAgent
from inside_game.api import create_app
from inside_game.mcp_server import McpSettings, create_server, tool_catalog
from inside_game.providers.models import (
    AzureChatModel,
    AzureModelSettings,
    AzureResponsesModel,
    ModelFailure,
    ModelTurn,
    inline_tool_schema,
)
from inside_game.settings import Settings
from inside_game.tools.mcp_client import DataMcpSettings


def tool(name, args):
    return {
        "type": "function_call",
        "call_id": name,
        "name": name,
        "arguments": json.dumps(args),
    }


def finish(ids, status="complete", clarification=None):
    return tool(
        "finish_data_request",
        {
            "status": status,
            "evidence_ids": ids,
            "clarification": clarification,
            "notes": [],
        },
    )


class ScriptedModel:
    name = "test-model-not-luna"

    def __init__(self, *turns):
        self.turns = list(turns)
        self.seen = []

    async def respond(self, instructions, messages, tools):
        self.seen.append(json.loads(json.dumps(messages)))
        assert "SQL" in instructions
        assert "finish_data_request" in {t["name"] for t in tools}
        value = self.turns.pop(0)
        if isinstance(value, Exception):
            raise value
        return ModelTurn(value if isinstance(value, list) else [value], 50)


def payload(name="get_shots", *, data=None, next_cursor=None):
    return {
        "operation_id": name,
        "method_id": name + "_v1",
        "request_id": "upstream-1",
        "scope": {"match_id": 900001},
        "data": data or {"total": 2},
        "provenance": {"is_synthetic": True},
        "coverage": {"match_count": 1},
        "coordinates": {"events": "acting_team_120x80"},
        "pagination": {"next_cursor": next_cursor},
        "warnings": ["Synthetic xG"],
    }


def success(value):
    return CallToolResult(structured_content=value, content=[])


def failure(code):
    return CallToolResult(
        is_error=True,
        content=[
            TextContent(
                type="text",
                text=json.dumps({"error": {"code": code, "message": "SECRET"}}),
            )
        ],
    )


class FakeMcp:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    async def list_tools(self):
        return SimpleNamespace(tools=tool_catalog())

    async def call_tool(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        return self.results.pop(0)


def run(model, mcp, *, text="Dame los tiros del partido 900001", limits=None):
    return asyncio.run(DataAgent(model, limits=limits).run(text, mcp))


def test_text_to_multiple_players_through_real_mcp_and_api(repository):
    async def scenario():
        model = ScriptedModel(
            tool("get_shots", {"match_id": 900001, "player_id": 106}),
            tool("get_shots", {"match_id": 900001, "player_id": 110}),
            finish(["e1", "e2"]),
        )
        api = create_app(Settings(), repository)
        server = create_server(McpSettings(), httpx.ASGITransport(app=api))
        async with Client(server) as client:
            result = await DataAgent(model).run(
                {
                    "request_text": "Necesito comparar los tiros de estos jugadores",
                    "context": {"match_ids": [900001], "player_ids": [106, 110]},
                },
                client,
            )
            assert result.status == "complete"
            assert [e.arguments["player_id"] for e in result.evidence] == [106, 110]
            for evidence in result.evidence:
                direct = await client.call_tool(evidence.operation, evidence.arguments)
                assert evidence.response.data == direct.structured_content["data"]
                assert evidence.response.provenance["is_synthetic"]
                assert evidence.response.coordinates and evidence.response.warnings

    asyncio.run(scenario())


def test_ambiguity_returns_question_to_caller_without_query():
    mcp = FakeMcp()
    result = run(
        ScriptedModel(finish([], "needs_clarification", "¿Qué partido del Liverpool?")),
        mcp,
    )
    assert result.status == "needs_clarification" and result.clarification
    assert mcp.calls == []


def test_invalid_sql_does_not_reach_mcp_and_can_be_corrected():
    model = ScriptedModel(
        tool("get_shots", {"match_id": 900001, "sql": "SECRET"}),
        tool("get_shots", {"match_id": 900001}),
        finish(["e1"]),
    )
    mcp = FakeMcp(success(payload()))
    result = run(model, mcp)
    assert result.status == "complete" and len(mcp.calls) == 1
    error = json.loads(model.seen[1][-1]["output"])
    assert error["error"]["code"] == "INVALID_ARGUMENT"
    assert "SECRET" not in json.dumps(error)


def test_unknown_tool_and_forged_evidence_are_rejected():
    model = ScriptedModel(
        tool("execute_sql", {"query": "SELECT 1"}),
        finish(["forged"]),
        finish([], "unsupported"),
    )
    mcp = FakeMcp()
    result = run(model, mcp)
    assert result.status == "unsupported" and not mcp.calls
    assert "UNREGISTERED_OPERATION" in model.seen[1][-1]["output"]
    assert "UNKNOWN_EVIDENCE_ID" in model.seen[2][-1]["output"]


def test_pagination_keeps_filters_and_original_values():
    p1 = payload(data={"rows": [{"x": 1.23456789}]}, next_cursor="opaque")
    p2 = payload(data={"rows": [{"x": 98.7654321}]})
    mcp = FakeMcp(success(p1), success(p2))
    result = run(
        ScriptedModel(
            tool("get_shots", {"match_id": 900001, "team_id": 1}), finish(["e1", "e2"])
        ),
        mcp,
    )
    assert result.status == "complete" and result.tool_calls == 2
    assert {**mcp.calls[0][1], "cursor": "opaque"} == mcp.calls[1][1]
    assert result.evidence[1].response.data == p2["data"]


def test_omitting_a_page_cannot_be_complete():
    mcp = FakeMcp(success(payload(next_cursor="next")), success(payload()))
    result = run(
        ScriptedModel(tool("get_shots", {"match_id": 900001}), finish(["e1"])), mcp
    )
    assert result.status == "partial"
    assert result.issues[-1].code == "INCOMPLETE_EVIDENCE_SELECTION"


def test_page_budget_marks_partial_even_if_model_claims_complete():
    mcp = FakeMcp(success(payload(next_cursor="next")))
    result = run(
        ScriptedModel(tool("get_shots", {"match_id": 900001}), finish(["e1"])),
        mcp,
        limits=AgentLimits(max_pages_per_query=1),
    )
    assert result.status == "partial" and result.tool_calls == 1
    assert "PAGE_BUDGET_EXCEEDED" in {i.code for i in result.issues}


def test_duplicate_queries_are_reused():
    query = tool("get_shots", {"match_id": 900001})
    mcp = FakeMcp(success(payload()))
    result = run(ScriptedModel(query, query, finish(["e1"])), mcp)
    assert result.status == "complete" and len(mcp.calls) == 1


def test_complete_cannot_omit_an_entire_analytical_query():
    model = ScriptedModel(
        tool("get_shots", {"match_id": 900001, "player_id": 106}),
        tool("get_shots", {"match_id": 900001, "player_id": 110}),
        finish(["e1"]),
        finish(["e1", "e2"]),
    )
    result = run(model, FakeMcp(success(payload()), success(payload())))
    assert result.status == "complete" and len(result.evidence) == 2
    assert "OMITTED_QUERY_EVIDENCE" in model.seen[3][-1]["output"]
    assert len(result.prompt_sha256) == 64


def test_catalog_preview_does_not_hide_real_matches_after_synthetic_ones():
    items = [{"match_id": 900001 + i, "is_synthetic": i < 10} for i in range(20)]
    model = ScriptedModel(tool("list_matches", {}), finish(["e1"]))
    result = run(
        model, FakeMcp(success(payload("list_matches", data={"items": items})))
    )
    visible = json.loads(model.seen[1][-1]["output"])
    assert visible["pages"][0]["response_preview"]["data"]["items"] == items
    assert result.evidence[0].response.data["items"] == items


def test_finish_mixed_with_queries_does_not_drop_later_calls():
    query = tool("get_shots", {"match_id": 900001})
    model = ScriptedModel([finish([], "unsupported"), query], query, finish(["e1"]))
    mcp = FakeMcp(success(payload()))
    result = run(model, mcp)
    assert result.status == "complete" and len(mcp.calls) == 1
    assert all("FINISH_MUST_BE_SEPARATE" in m["output"] for m in model.seen[1][-2:])


def test_mcp_auth_failure_stops_without_model_retry():
    model = ScriptedModel(tool("get_shots", {"match_id": 900001}))
    result = run(model, FakeMcp(failure("UNAUTHORIZED")))
    assert result.status == "error" and result.tool_calls == 1
    assert result.issues[-1].code == "UNAUTHORIZED"
    assert "SECRET" not in result.model_dump_json()


def test_transient_mcp_failure_has_one_retry():
    mcp = FakeMcp(failure("BUSY"), success(payload()))
    result = run(
        ScriptedModel(tool("get_shots", {"match_id": 900001}), finish(["e1"])), mcp
    )
    assert result.status == "complete" and result.tool_calls == 2


def test_call_budget_returns_existing_evidence():
    mcp = FakeMcp(success(payload(next_cursor="next")))
    result = run(
        ScriptedModel(tool("get_shots", {"match_id": 900001})),
        mcp,
        limits=AgentLimits(max_tool_calls=1),
    )
    assert result.status == "partial" and len(result.evidence) == 1
    assert result.issues[-1].code == "TOOL_BUDGET_EXCEEDED"


def test_failed_later_query_cannot_be_silently_omitted_as_complete():
    mcp = FakeMcp(success(payload()), failure("NOT_FOUND"))
    model = ScriptedModel(
        tool("get_shots", {"match_id": 900001}),
        tool("get_shots", {"match_id": 900002}),
        finish(["e1"]),
    )
    result = run(model, mcp)
    assert result.status == "partial"


def test_rejected_arguments_can_be_corrected_without_permanent_partial_status():
    model = ScriptedModel(
        tool(
            "get_defensive_actions",
            {"match_id": 900001, "kind": "all", "outcome": "won"},
        ),
        tool(
            "get_defensive_actions",
            {"match_id": 900001, "kind": "aerial_duel", "outcome": "won"},
        ),
        finish(["e1"]),
    )
    result = run(
        model,
        FakeMcp(failure("INVALID_ARGUMENT"), success(payload("get_defensive_actions"))),
    )
    assert result.status == "complete" and len(result.evidence) == 1
    assert result.issues[0].code == "INVALID_ARGUMENT"
    assert json.loads(model.seen[1][-1]["output"])["complete"] is False


def test_rejected_later_page_still_means_incomplete_evidence():
    model = ScriptedModel(tool("get_shots", {"match_id": 900001}), finish(["e1"]))
    result = run(
        model,
        FakeMcp(success(payload(next_cursor="next")), failure("INVALID_ARGUMENT")),
    )
    assert result.status == "partial"


def test_model_failure_returns_partial_and_hides_exception():
    model = ScriptedModel(
        tool("get_shots", {"match_id": 900001}), ModelFailure("MODEL_UNAVAILABLE")
    )
    result = run(model, FakeMcp(success(payload())))
    assert result.status == "partial" and result.evidence
    assert result.issues[-1].code == "MODEL_UNAVAILABLE"


def test_mismatched_response_is_rejected():
    result = run(
        ScriptedModel(tool("get_shots", {"match_id": 900001})),
        FakeMcp(success(payload("get_passes"))),
    )
    assert result.status == "error" and not result.evidence


def test_deadline_cancels_model():
    class Slow(ScriptedModel):
        async def respond(self, *args):
            await asyncio.sleep(1)

    result = run(Slow(), FakeMcp(), limits=AgentLimits(timeout_seconds=0.01))
    assert result.status == "error" and result.issues[-1].code == "DEADLINE_EXCEEDED"


@pytest.mark.parametrize(
    "value",
    [
        {"request_text": "hola", "sql": "SELECT 1"},
        {"request_text": "hola", "context": {"player_ids": [True]}},
        {"request_text": "hola", "context": {"mcp_url": "https://evil.invalid/mcp"}},
    ],
)
def test_request_has_no_execution_controls(value):
    with pytest.raises(ValueError):
        DataRequest.model_validate(value)


@pytest.mark.parametrize(
    "url",
    [
        "http://evil.invalid/mcp",
        "https://host.invalid/other",
        "https://user:password@host.invalid/mcp",
    ],
)
def test_mcp_destination_validation(url):
    with pytest.raises(ValueError):
        DataMcpSettings(url, "x" * 40)


def test_responses_adapter_preserves_reasoning_and_configuration():
    seen = []
    reasoning = {"type": "reasoning", "encrypted_content": "opaque", "summary": []}

    def handler(request):
        seen.append(json.loads(request.content))
        assert request.url.path == "/openai/v1/responses"
        assert request.headers["api-key"] == "private-test-key"
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [reasoning],
                "usage": {"total_tokens": 25},
            },
        )

    async def scenario():
        settings = AzureModelSettings(
            "https://test.openai.azure.com", auth="api_key", api_key="private-test-key"
        )
        async with AzureResponsesModel(
            settings, transport=httpx.MockTransport(handler)
        ) as model:
            result = await model.respond(
                "instruction", [{"role": "user", "content": "hi"}], []
            )
            assert result.output == [reasoning] and result.total_tokens == 25
            await model.respond("instruction", result.output, [])

    asyncio.run(scenario())
    assert seen[1]["input"] == [reasoning]
    assert seen[0]["store"] is False and "temperature" not in seen[0]


def test_provider_error_sanitization():
    async def scenario():
        async with AzureResponsesModel(
            AzureModelSettings(
                "https://test.openai.azure.com", auth="api_key", api_key="SECRET"
            ),
            transport=httpx.MockTransport(
                lambda r: httpx.Response(401, text="SECRET AUTH BODY")
            ),
        ) as model:
            with pytest.raises(ModelFailure, match="MODEL_UNAUTHORIZED") as exc:
                await model.respond("instruction", [], [])
            assert "SECRET" not in str(exc.value)

    asyncio.run(scenario())


def test_provider_respects_retry_after_without_exposing_error_body(monkeypatch):
    waits = []
    attempts = []

    async def sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr("inside_game.providers.models.asyncio.sleep", sleep)

    def handler(request):
        attempts.append(request)
        if len(attempts) == 1:
            return httpx.Response(429, headers={"retry-after": "60"}, text="SECRET")
        return httpx.Response(
            200,
            json={"status": "completed", "output": [], "usage": {"total_tokens": 1}},
        )

    async def scenario():
        async with AzureResponsesModel(
            AzureModelSettings(
                "https://test.openai.azure.com", auth="api_key", api_key="private-test"
            ),
            transport=httpx.MockTransport(handler),
        ) as model:
            result = await model.respond("rules", [], [])
            assert result.total_tokens == 1

    asyncio.run(scenario())
    assert waits == [60] and len(attempts) == 2


def test_chat_adapter_retains_tool_call_ids_and_results():
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        assert request.url.path == "/openai/v1/chat/completions"
        assert body["tool_choice"] == "auto"
        assert "strict" not in body["tools"][0]["function"]
        call = {
            "id": "azure-call-123",
            "type": "function",
            "function": {"name": "get_shots", "arguments": '{"match_id":900001}'},
        }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [call],
                        },
                    }
                ],
                "usage": {"total_tokens": 30},
            },
        )

    async def scenario():
        settings = AzureModelSettings(
            "https://test.services.ai.azure.com",
            deployment="gpt-oss-120b",
            auth="api_key",
            api_key="test-only",
            api="chat_completions",
        )
        async with AzureChatModel(
            settings, transport=httpx.MockTransport(handler)
        ) as model:
            tool_def = {
                "type": "function",
                "name": "get_shots",
                "description": "shots",
                "parameters": {"type": "object", "properties": {}},
                "strict": False,
            }
            messages = [{"role": "user", "content": "tiros"}]
            turn = await model.respond("rules", messages, [tool_def])
            assert turn.output[1]["call_id"] == "azure-call-123"
            messages += turn.output + [
                {
                    "type": "function_call_output",
                    "call_id": "azure-call-123",
                    "output": '{"pages":[]}',
                }
            ]
            await model.respond("rules", messages, [tool_def])

    asyncio.run(scenario())
    followup = seen[1]["messages"]
    assert len([m for m in followup if m["role"] == "assistant"]) == 1
    assert followup[-1] == {
        "role": "tool",
        "tool_call_id": "azure-call-123",
        "content": '{"pages":[]}',
    }


def test_gpt_oss_schema_rendering_keeps_runtime_enum_validation():
    from inside_game.contracts import ShotsRequest

    schema = inline_tool_schema(ShotsRequest.model_json_schema())
    assert "$ref" not in json.dumps(schema) and "$defs" not in schema
    assert "enum" not in schema["properties"]["bin_s"]
    assert "300" in schema["properties"]["bin_s"]["description"]
    assert schema["properties"]["outcome"]["enum"]
    # La adaptación de visualización del modelo no permite valores adicionales.
    with pytest.raises(ValueError):
        ShotsRequest.model_validate({"match_id": 900001, "bin_s": 123})


def test_zero_is_not_missing_data():
    original = payload(data={"total": 0, "items": []})
    result = run(
        ScriptedModel(tool("get_shots", {"match_id": 900001}), finish(["e1"])),
        FakeMcp(success(original)),
    )
    assert result.status == "complete"
    assert result.evidence[0].response.data == {"total": 0, "items": []}


def test_auto_tool_choice_text_reply_is_corrected_without_fabricating_data():
    free_text = {
        "type": "chat_message",
        "message": {"role": "assistant", "content": "Hay 999 tiros"},
    }
    model = ScriptedModel(
        tool("get_shots", {"match_id": 900001}), free_text, finish(["e1"])
    )
    result = run(model, FakeMcp(success(payload(data={"total": 2}))))
    assert (
        result.status == "complete" and result.evidence[0].response.data["total"] == 2
    )
    assert result.model_turns == 3 and result.tool_calls == 1
    assert "Hay 999 tiros" not in result.model_dump_json()


def test_text_reply_corrections_are_bounded():
    free_text = {
        "type": "chat_message",
        "message": {"role": "assistant", "content": "texto"},
    }
    result = run(ScriptedModel(free_text, free_text, free_text), FakeMcp())
    assert result.status == "error" and result.model_turns == 3
    assert result.issues[-1].code == "MODEL_EXPECTED_TOOL_CALL"


def test_no_numeric_result_can_be_fabricated_in_finish():
    model = ScriptedModel(finish([]), finish([], "unsupported"))
    result = run(model, FakeMcp())
    assert result.status == "unsupported" and not result.evidence
    assert "EVIDENCE_REQUIRED" in model.seen[1][-1]["output"]


def test_turn_budget_stops_repeated_invalid_calls():
    model = ScriptedModel(tool("execute_sql", {}))
    result = run(model, FakeMcp(), limits=AgentLimits(max_turns=1))
    assert result.status == "error" and result.issues[-1].code == "TURN_BUDGET_EXCEEDED"


def test_private_credential_file_is_not_sent_to_model(tmp_path, monkeypatch):
    private = tmp_path / "agent-data.json"
    private.write_text(
        json.dumps({"credential_id": "agent-data", "key": "secret" * 10})
    )
    monkeypatch.delenv("INSIDE_GAME_DATA_MCP_KEY", raising=False)
    monkeypatch.setenv("INSIDE_GAME_DATA_MCP_CREDENTIAL_FILE", str(private))
    settings = DataMcpSettings.from_env()
    assert settings.key == "secret" * 10 and "secret" not in repr(settings)


def test_concurrent_runs_keep_evidence_separate():
    class IndependentModel:
        name = "test-model"

        async def respond(self, instructions, messages, tools):
            await asyncio.sleep(0)
            request = json.loads(messages[0]["content"])
            call = (
                tool("get_shots", {"match_id": request["context"]["match_ids"][0]})
                if len(messages) == 1
                else finish(["e1"])
            )
            return ModelTurn([call])

    async def scenario():
        agent = DataAgent(IndependentModel())
        a, b = await asyncio.gather(
            agent.run(
                {"request_text": "A", "context": {"match_ids": [900001]}},
                FakeMcp(success(payload(data={"source": "A"}))),
            ),
            agent.run(
                {"request_text": "B", "context": {"match_ids": [900002]}},
                FakeMcp(success(payload(data={"source": "B"}))),
            ),
        )
        assert a.request_id != b.request_id
        assert a.evidence[0].response.data == {"source": "A"}
        assert b.evidence[0].response.data == {"source": "B"}

    asyncio.run(scenario())
