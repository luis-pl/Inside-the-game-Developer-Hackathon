"""Context pressure, temporal selectors and episode evidence regressions."""

import asyncio
import copy
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_data_agent import FakeMcp, payload, success
from test_sports_analyst import RouterModel, evidence_result

from inside_game.agents.analyst_contracts import AnalysisRequest
from inside_game.agents.analyst_facts import evidence_facts
from inside_game.agents.context_window import (
    ContextWindow,
    pending_calls,
)
from inside_game.agents.contracts import DataRequest, Evidence
from inside_game.agents.data_agent import DataAgent
from inside_game.agents.data_agent import _Run as DataRun
from inside_game.agents.sports_analyst import SportsAnalyst
from inside_game.agents.sports_analyst import _Run as AnalystRun
from inside_game.providers.models import ModelFailure, ModelTurn, token_usage
from inside_game.service import OPERATIONS


def closed_history(root, padding=4000):
    return [
        {"role": "user", "content": json.dumps(root)},
        {
            "type": "chat_message",
            "message": {
                "role": "assistant",
                "content": None,
                "reasoning_content": "private reasoning " * padding,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "fetch", "arguments": "{}"},
                    }
                ],
            },
        },
        {
            "type": "function_call",
            "call_id": "call-1",
            "name": "fetch",
            "arguments": "{}",
        },
        {
            "type": "function_call_output",
            "call_id": "call-1",
            "output": '{"error":{"code":"INVALID_ARGUMENT","fields":[{"path":["period"],"type":"int_type"}]}}',
        },
    ]


def test_compaction_preserves_request_tools_and_exact_authoritative_state():
    root = {
        "request_id": str(uuid4()),
        "request_text": "Keep every pass and both teams",
        "language": "fr",
        "context": {
            "match_ids": [900011],
            "scope": {"kind": "window", "period": 2, "start_ms": 0, "end_ms": 20000},
        },
    }
    evidence = {
        "evidence_id": "e1",
        "query_id": "q1",
        "provenance": {"is_synthetic": False},
        "coverage": {"missing": 3},
        "warnings": ["Do not fill gaps"],
        "method_id": "observed",
        "pagination": {"next_cursor": None},
        "coordinates": "fixed_tracking",
        "complete": True,
    }
    checkpoint = {**root, "evidence": [evidence]}
    history = closed_history(root)
    tools = [{"name": name, "parameters": {}} for name in OPERATIONS]
    originals = copy.deepcopy((checkpoint, tools))
    window = ContextWindow(15000)
    window.prepare(
        SimpleNamespace(),
        "scientific rules",
        history,
        tools,
        lambda: copy.deepcopy(checkpoint),
    )
    assert window.events[-1]["compacted"] and len(history) == 1
    state = json.loads(history[0]["content"])
    for key, value in checkpoint.items():
        assert state[key] == value
    assert (
        state["context_checkpoint"]["recent_errors"][0]["error"]["code"]
        == "INVALID_ARGUMENT"
    )
    assert "private reasoning" not in history[0]["content"]
    assert tools == originals[1] and checkpoint == originals[0]
    assert not pending_calls(history)


def test_below_threshold_never_calls_checkpoint_or_mutates_history():
    history = [{"role": "user", "content": '{"request_id":"same-session"}'}]
    original = copy.deepcopy(history)
    window = ContextWindow(10000)
    window.prepare(
        SimpleNamespace(),
        "rules",
        history,
        [],
        lambda: pytest.fail("Unnecessary compaction"),
    )
    assert history == original and window.events[-1]["reason"] == "below_threshold"


def test_open_tool_batch_is_never_compacted_or_left_dangling():
    history = closed_history({"request_id": str(uuid4())})[:-1]
    original = copy.deepcopy(history)
    assert pending_calls(history) == {"call-1"}
    window = ContextWindow(1000)
    with pytest.raises(ModelFailure, match="CONTEXT_BUDGET_EXCEEDED"):
        window.prepare(
            SimpleNamespace(), "rules", history, [], lambda: pytest.fail("Open batch")
        )
    assert history == original and not window.events[-1]["compacted"]


def test_oversized_authoritative_checkpoint_fails_without_silent_truncation():
    root = {"request_id": str(uuid4()), "request_text": "important" * 1000}
    history = closed_history(root)
    with pytest.raises(ModelFailure, match="CONTEXT_BUDGET_EXCEEDED"):
        ContextWindow(1000).prepare(
            SimpleNamespace(), "rules", history, [], lambda: root.copy()
        )
    assert json.loads(history[0]["content"])["request_text"] == root["request_text"]


def test_native_token_limit_is_unknown_until_published_and_estimate_is_labeled():
    model = SimpleNamespace(settings=SimpleNamespace(max_output_tokens=10))
    history = [
        {
            "role": "user",
            "content": json.dumps({"request_id": str(uuid4()), "task": "x" * 100}),
        }
    ]
    window = ContextWindow(100000)
    window.prepare(model, "rules", history, [], dict)
    assert window.events[-1]["native_window_tokens"] is None
    assert window.events[-1]["estimated_input_tokens"] is None
    window.observe(ModelTurn([], input_tokens=900))
    model.context_window_tokens = 1000
    window.prepare(
        model, "rules", history, [], lambda: json.loads(history[0]["content"])
    )
    assert window.events[-1]["estimated_input_tokens"] == 900
    assert window.events[-1]["native_window_tokens"] == 1000


@pytest.mark.parametrize(
    "payload_value,expected",
    [
        ({}, {"input_tokens": None, "output_tokens": None, "cached_tokens": None}),
        (
            {
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "prompt_tokens_details": {"cached_tokens": 80},
                }
            },
            {"input_tokens": 100, "output_tokens": 20, "cached_tokens": 80},
        ),
        (
            {
                "usage": {
                    "input_tokens": 200,
                    "output_tokens": 30,
                    "input_tokens_details": {"cached_tokens": 150},
                }
            },
            {"input_tokens": 200, "output_tokens": 30, "cached_tokens": 150},
        ),
        (
            {"usage": {"input_tokens": True, "output_tokens": -1}},
            {"input_tokens": None, "output_tokens": None, "cached_tokens": None},
        ),
    ],
)
def test_usage_keeps_unknowns_null_and_cache_as_subset(payload_value, expected):
    assert token_usage(payload_value) == expected


def test_analyst_checkpoint_rehydrates_all_current_facts_and_resets_delta():
    state = AnalystRun(
        SportsAnalyst(RouterModel()),
        AnalysisRequest(
            request_text="Reconstruct", original_request="All passes", language="pt"
        ),
    )
    state.merge(evidence_result())
    before = copy.deepcopy(state.facts)
    state.catalog_delta()
    checkpoint = state.checkpoint()
    assert {f["id"] for f in checkpoint["facts"]} == {f.id for f in before}
    assert not checkpoint["catalog_is_delta"]
    assert checkpoint["request"]["original_request"] == "All passes"
    assert state.catalog_delta()["facts"] == [] and state.facts == before


def data_state(context, operation, response=None):
    state = DataRun(
        DataAgent(RouterModel()),
        DataRequest(request_text="Evidence", context=context),
        FakeMcp(success(response or payload(operation))),
    )
    state.tools = {operation: None}
    return state


def test_spatial_point_narrows_selected_window_without_injecting_incompatible_scope():
    state = data_state(
        {
            "match_ids": [900011],
            "team_ids": [102],
            "scope": {
                "kind": "window",
                "period": 1,
                "start_ms": 600000,
                "end_ms": 602000,
            },
        },
        "get_team_shape",
    )
    result = asyncio.run(state.query("get_team_shape", {"time_ms": 601000}))
    assert result["complete"]
    args = state.mcp.calls[0][1]
    assert (
        args["period"] == 1
        and args["time_ms"] == 601000
        and args["scope"] == {"kind": "match"}
    )


@pytest.mark.parametrize("time_ms", [599999, 602000, 700000])
def test_spatial_point_cannot_escape_half_open_context_window(time_ms):
    state = data_state(
        {
            "scope": {
                "kind": "window",
                "period": 1,
                "start_ms": 600000,
                "end_ms": 602000,
            }
        },
        "get_team_shape",
    )
    result = asyncio.run(
        state.query(
            "get_team_shape", {"match_id": 900011, "team_id": 102, "time_ms": time_ms}
        )
    )
    assert result["error"]["code"] == "CONTEXT_SCOPE_MISMATCH" and not state.mcp.calls


def test_tracking_sampling_is_explicit_and_relational_population_not_filtered():
    state = data_state(
        {
            "match_ids": [900011],
            "team_ids": [103],
            "sample_step_ms": 200,
            "scope": {"kind": "window", "period": 1, "start_ms": 0, "end_ms": 20000},
        },
        "get_tracking_window",
    )
    result = asyncio.run(state.query("get_tracking_window", {}))
    assert result["complete"]
    args = state.mcp.calls[0][1]
    assert args["sample_step_ms"] == 200 and args["stride_s"] == 1
    assert args["team_id"] is None
    bad = asyncio.run(state.query("get_tracking_window", {"sample_step_ms": 1000}))
    assert bad["error"]["code"] == "CONTEXT_RESOLUTION_MISMATCH"


def test_recorded_pass_links_use_source_names_order_and_timestamps_only():
    source = evidence_result().evidence[0].model_dump(mode="json")
    source.update(
        evidence_id="passes",
        query_id="passes",
        operation="get_passes",
        arguments={"match_id": 900011},
    )
    source["response"].update(
        operation_id="get_passes",
        data={
            "total": 1,
            "items": [
                {
                    "timestamp": "00:00:01.760",
                    "period": 1,
                    "player_id": 10,
                    "event_id": "recorded-id",
                    "pass": {"recipient_player_id": 20},
                }
            ],
        },
    )
    context = copy.deepcopy(source)
    context.update(
        evidence_id="context", query_id="context", operation="get_match_context"
    )
    context["response"].update(
        operation_id="get_match_context",
        data={
            "lineups": [
                {"player_id": 10, "player_name": "Source A"},
                {"player_id": 20, "player_name": "Source B"},
            ]
        },
    )
    tracking = copy.deepcopy(source)
    tracking.update(evidence_id="tracking", operation="get_tracking_window")
    tracking["response"].update(operation_id="get_tracking_window", data={"frames": []})
    facts = evidence_facts(
        [Evidence.model_validate(e) for e in [source, context, tracking]]
    )
    links = [f for f in facts if f.label == "recorded_pass_link"]
    assert len(links) == 1 and links[0].value == "00:00:01.760 · Source A → Source B"
    assert links[0].scope["endpoint_observations_only"] is True
    source["response"]["data"]["total"] = 10
    facts = evidence_facts(
        [Evidence.model_validate(e) for e in [source, context, tracking]]
    )
    assert not any(f.label == "recorded_pass_link" for f in facts)


def test_http_deadline_keeps_evidence_instead_of_racing_inner_timeout(monkeypatch):
    from contextlib import asynccontextmanager

    import httpx
    from test_data_agent import tool
    from test_sports_analyst import KEY, records

    from inside_game.agents import http_api

    @asynccontextmanager
    async def delayed_mcp(settings):
        await asyncio.sleep(0.15)
        yield FakeMcp(success(payload()))

    class Model(RouterModel):
        calls = 0

        async def respond(self, instructions, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return ModelTurn([tool("get_shots", {"match_id": 900001})])
            await asyncio.sleep(2)
            return ModelTurn([])

    monkeypatch.setattr(http_api, "connect_data_mcp", delayed_mcp)
    app = http_api.create_agent_app(credentials=records(), model_factory=Model)

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": "Bearer " + KEY},
        ) as client:
            response = await client.post(
                "/a2a/v1/data",
                json={"request_text": "Shots"},
                headers={"X-Agent-Deadline-Ms": "1000"},
            )
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "partial" and len(result["evidence"]) == 1
        assert result["model_turns"] == 1 and result["context_events"]
        assert any(i["code"] == "DEADLINE_EXCEEDED" for i in result["issues"])

    asyncio.run(scenario())


def test_progressive_schemas_keep_every_capability_discoverable_without_keyword_routing():
    from test_data_agent import finish, tool

    class Model:
        name = "offline"
        calls = 0

        async def respond(self, instructions, messages, tools):
            self.calls += 1
            root = json.loads(messages[0]["content"])
            assert {t["name"] for t in root["tool_catalog"]} == set(OPERATIONS)
            enabled = {t["name"] for t in tools}
            if self.calls == 1:
                assert "get_node_removal_robustness" not in enabled
                assert "describe_data_tools" in enabled
                return ModelTurn(
                    [tool("describe_data_tools", {"tool_names": list(OPERATIONS)})]
                )
            assert set(OPERATIONS) <= enabled
            return ModelTurn(
                [
                    finish(
                        [], status="needs_clarification", clarification="Which instant?"
                    )
                ]
            )

    result = asyncio.run(DataAgent(Model()).run("Analysiere die Mannschaft", FakeMcp()))
    assert result.status == "needs_clarification" and result.tool_calls == 0
    assert result.tool_trace[0]["tool"] == "describe_data_tools"


def test_progressive_discovery_rejects_foreign_tools_and_retains_known_schemas():
    from test_data_agent import finish, tool

    class Model:
        name = "offline"
        calls = 0

        async def respond(self, instructions, messages, tools):
            self.calls += 1
            enabled = {t["name"] for t in tools}
            if self.calls == 1:
                return ModelTurn(
                    [
                        tool(
                            "describe_data_tools",
                            {"tool_names": ["execute_arbitrary_sql"]},
                        )
                    ]
                )
            if self.calls == 2:
                assert "UNKNOWN_TOOL_SCHEMA" in messages[-1]["output"]
                return ModelTurn(
                    [tool("describe_data_tools", {"tool_names": ["get_shots"]})]
                )
            assert "get_shots" in enabled and "execute_arbitrary_sql" not in enabled
            if self.calls == 3:
                return ModelTurn([tool("get_shots", {"match_id": 900001})])
            return ModelTurn([finish(["e1"])])

    mcp = FakeMcp(success(payload()))
    result = asyncio.run(DataAgent(Model()).run("Question", mcp))
    assert result.status == "complete" and len(mcp.calls) == 1


def test_progressive_named_operations_load_at_start_without_discovery_round():
    from test_data_agent import finish

    class Model:
        name = "offline"

        async def respond(self, instructions, messages, tools):
            assert {"get_passes", "get_tracking_window"} <= {t["name"] for t in tools}
            return ModelTurn(
                [
                    finish(
                        [], status="needs_clarification", clarification="Which window?"
                    )
                ]
            )

    result = asyncio.run(
        DataAgent(Model()).run("get_passes + get_tracking_window", FakeMcp())
    )
    assert result.status == "needs_clarification" and result.model_turns == 1


@pytest.mark.parametrize("nested_provenance", [False, True])
def test_unannotated_source_zero_cannot_become_a_fact_or_chart_metric(
    nested_provenance,
):
    from inside_game.insights.demo import demo_manifest
    from inside_game.insights.pages import compile_report

    manifest = demo_manifest()
    block = next(b for b in manifest["blocks"] if b["insight_id"] == "pass_map")
    evidence = [
        Evidence.model_validate(e)
        for e in manifest["evidence"]
        if e["evidence_id"] in block["evidence_ids"]
    ]
    for ev in evidence:
        ev.response.provenance.update(is_synthetic=False, provider="Metrica Sports")
        if nested_provenance:
            ev.response.provenance.pop("provider")
            ev.response.provenance["datasets"] = [
                {"provider": "Metrica Sports", "data_kind": "real_anonymized"}
            ]
        ev.response.data.setdefault("summary", {}).update(cross=0, cut_back=0, switch=0)
    originals = copy.deepcopy(evidence)
    facts = evidence_facts(evidence)
    assert not {"cross", "cut_back", "switch"} & {f.label for f in facts}
    _, (compiled,) = compile_report({"blocks": [block], "evidence": evidence})
    assert not any(
        k.rsplit(".", 1)[-1] in {"cross", "cut_back", "switch"}
        for k in compiled.metrics
    )
    assert evidence == originals


def test_progressive_full_schema_restores_subwindows_without_losing_coverage():
    from test_data_agent import finish, tool

    class Model:
        name = "offline"
        calls = 0

        async def respond(self, instructions, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return ModelTurn(
                    [
                        tool(
                            "describe_data_tools",
                            {
                                "tool_names": ["get_tracking_window"],
                                "full_schema": True,
                            },
                        )
                    ]
                )
            schema = next(
                t["parameters"] for t in tools if t["name"] == "get_tracking_window"
            )
            assert "scope" in schema["properties"]
            if self.calls in {2, 3}:
                start = (self.calls - 2) * 20000
                return ModelTurn(
                    [
                        tool(
                            "get_tracking_window",
                            {
                                "match_id": 900001,
                                "scope": {
                                    "kind": "window",
                                    "period": 1,
                                    "start_ms": start,
                                    "end_ms": start + 20000,
                                },
                            },
                        )
                    ]
                )
            return ModelTurn([finish(["e1", "e2"])])

    context = {
        "match_ids": [900001],
        "scope": {"kind": "window", "period": 1, "start_ms": 0, "end_ms": 40000},
    }
    mcp = FakeMcp(
        success(payload("get_tracking_window")), success(payload("get_tracking_window"))
    )
    result = asyncio.run(
        DataAgent(Model()).run(DataRequest(request_text="Replay", context=context), mcp)
    )
    assert result.status == "complete" and len(result.evidence) == 2
    assert [(a["scope"]["start_ms"], a["scope"]["end_ms"]) for _, a in mcp.calls] == [
        (0, 20000),
        (20000, 40000),
    ]


def test_insights_rejects_duplicate_charts_when_one_combined_chart_requested():
    from inside_game.agents.insight_contracts import InsightRequest
    from inside_game.agents.page_builder import DashboardBuilder, _InsightRun
    from inside_game.insights.demo import demo_manifest

    manifest = demo_manifest()
    block = next(b for b in manifest["blocks"] if b["insight_id"] == "shot_map")
    state = _InsightRun(
        DashboardBuilder(RouterModel()),
        InsightRequest(
            request_text="One map for both teams", required_insights=["shot_map"]
        ),
        None,
        [],
    )
    blocks = [{**block, "id": "home"}, {**block, "id": "away"}]
    output, result = asyncio.run(state.call("render_report", {"blocks": blocks}))
    assert result is None and output["error"] == "REQUESTED_INSIGHTS_MISMATCH"
    assert output["required_insights"] == ["shot_map"]


def test_unknown_requested_recipe_is_rejected_before_agent_execution():
    from pydantic import ValidationError

    from inside_game.agents.insight_contracts import InsightRequest

    with pytest.raises(ValidationError):
        InsightRequest(request_text="Graph", required_insights=["invented_metric"])


def test_source_names_with_digits_are_grounded_without_hiding_arbitrary_numbers():
    from inside_game.agents.sports_analyst import ground_source_literals

    facts = [
        SimpleNamespace(
            id="name",
            label="player_name",
            value="M1 Jugador 19",
            scope={"match_id": 900011},
        ),
        SimpleNamespace(
            id="numeric", label="player_name", value="99", scope={"match_id": 900011}
        ),
        SimpleNamespace(
            id="rate", label="sampling_hz", value=5, scope={"match_id": 900011}
        ),
    ]
    assert (
        ground_source_literals("M1 Jugador 19 a 5 Hz; 99 tiros y 10 Hz.", facts)
        == "{{name}} a {{rate}} Hz; 99 tiros y 10 Hz."
    )
    assert ground_source_literals("M1 Jugador 190", facts) == "M1 Jugador 190"
    facts.append(
        SimpleNamespace(
            id="other", label="team_name", value="Team 2", scope={"match_id": 900001}
        )
    )
    assert ground_source_literals("M1 Jugador 19", facts) == "M1 Jugador 19"


def test_native_limit_blocks_estimated_overflow_even_below_application_bytes():
    model = SimpleNamespace(
        context_window_tokens=100, settings=SimpleNamespace(max_output_tokens=10)
    )
    history = [{"role": "user", "content": "x" * 1000}]
    window = ContextWindow(100000)
    window.tokens_per_byte = 1
    with pytest.raises(ModelFailure, match="CONTEXT_BUDGET_EXCEEDED"):
        window.prepare(model, "rules", history, [], lambda: {"task": "y" * 1000})
    assert window.events[-1]["reason"] == "native_context_budget_exceeded"
