"""Invariantes matemáticos, datos ausentes, evidencia y MCP del renderer atómico."""

import asyncio
import copy
from html.parser import HTMLParser

import pytest
from mcp import Client

from inside_game.insights import advanced
from inside_game.insights.catalog import RECIPES
from inside_game.insights.contracts import Parameters, ReportSpec
from inside_game.insights.demo import demo_manifest
from inside_game.insights.mcp_server import create_server
from inside_game.insights.pages import compile_report, render_report
from inside_game.service import OPERATIONS


def one_block(key):
    manifest = demo_manifest()
    manifest["blocks"] = [b for b in manifest["blocks"] if b["insight_id"] == key]
    return manifest


def test_unknown_provenance_is_never_presented_as_recorded_data():
    manifest = one_block("shot_map")
    for evidence in manifest["evidence"]:
        evidence["response"]["provenance"].pop("is_synthetic", None)
    html = render_report(manifest)["html"]
    assert "Provenance not specified" in html
    assert "Mixed or unspecified provenance" in html
    assert "Recorded · see provider" not in html


def test_thirty_recipes_all_bind_real_registered_operations():
    assert len(RECIPES) == 30
    assert all(set(r["source_operations"]) <= set(OPERATIONS) for r in RECIPES.values())
    _, blocks = compile_report(demo_manifest())
    assert len(blocks) == 30
    assert all(b.state == "ready" for b in blocks)


def test_hodge_triangle_changes_with_complex_but_reconstructs():
    edges = [
        {"source": 1, "target": 2, "passes": 1},
        {"source": 2, "target": 3, "passes": 1},
        {"source": 3, "target": 1, "passes": 1},
    ]
    clique = advanced.hodge(edges, "clique")
    graph = advanced.hodge(edges, "graph")
    assert clique["fractions"]["curl"] == pytest.approx(1)
    assert graph["fractions"]["harmonic"] == pytest.approx(1)
    assert clique["fractions"]["gradient"] == pytest.approx(0, abs=1e-12)
    assert clique["orthogonality_error"] < 1e-12
    assert sum(clique["energies"].values()) == pytest.approx(clique["energy"])
    assert clique["reconstruction_error"] < 1e-12


def test_hodge_tree_and_balanced_flow():
    tree = advanced.hodge(
        [
            {"source": 1, "target": 2, "passes": 4},
            {"source": 2, "target": 3, "passes": 2},
        ]
    )
    assert tree["fractions"]["gradient"] == pytest.approx(1)
    zero = advanced.hodge(
        [
            {"source": 1, "target": 2, "passes": 4},
            {"source": 2, "target": 1, "passes": 4},
        ]
    )
    assert zero["energy"] == 0 and zero["fractions"] is None


def test_line_geometry_reflection_invariance_and_no_guessed_roles():
    frame = {
        "players": [
            {"player_id": 1, "team_id": 1, "x_m": 20, "y_m": 30},
            {"player_id": 2, "team_id": 1, "x_m": 25, "y_m": 40},
            {"player_id": 3, "team_id": 1, "x_m": 5, "y_m": 34},
        ]
    }
    p = Parameters(
        team_id=1, defender_ids=[1, 2], goalkeeper_id=3, attack_positive_x=True
    )
    first = advanced.goalkeeper_connection(frame, p)
    reflected = {"players": [{**v, "x_m": 105 - v["x_m"]} for v in frame["players"]]}
    second = advanced.goalkeeper_connection(
        reflected, p.model_copy(update={"attack_positive_x": False})
    )
    assert first == second
    assert first["defensive_line_height_m"] == 20
    assert first["longitudinal_gap_m"] == 15
    with pytest.raises(ValueError):
        advanced.line_geometry(frame, Parameters(team_id=1))


def test_final_third_crossing_and_unknown_outcomes():
    events = [
        {
            "event_id": "a",
            "location_x": 79,
            "location_y": 10,
            "pass": {"end_x": 80, "end_y": 80, "outcome": None},
        },
        {
            "event_id": "b",
            "location_x": 80,
            "location_y": 10,
            "pass": {"end_x": 90, "end_y": 10, "outcome": None},
        },
        {
            "event_id": "c",
            "location_x": 70,
            "location_y": 10,
            "pass": {"end_x": 90, "end_y": 10, "outcome": {"name": "Unknown"}},
        },
    ]
    rows = advanced.final_third_entries(events)
    assert len(rows) == 1 and rows[0]["channel"] == 4


def test_structural_pass_uses_tracked_participants_and_floored_ratio():
    frame = {
        "period": 1,
        "period_time_ms": 10000,
        "players": [
            {"player_id": 1, "team_id": 1, "x_m": 30, "y_m": 34},
            {"player_id": 2, "team_id": 1, "x_m": 60, "y_m": 34},
        ]
        + [
            {"player_id": 100 + x, "team_id": 2, "x_m": x, "y_m": 34}
            for x in (40, 50, 70)
        ],
    }
    event = {
        "event_id": "pass",
        "team_id": 1,
        "player_id": 1,
        "period": 1,
        "period_time_ms": 10000,
        "location_x": 10,
        "location_y": 20,
        "pass": {"end_x": 110, "end_y": 20, "recipient_player_id": 2, "outcome": None},
    }
    result = advanced.structural_pass(
        [event], [frame], Parameters(team_id=1, attack_positive_x=True)
    )
    assert result[0]["line_bypass_count"] == 2
    assert result[0]["relative_space_gain"] == pytest.approx(1)
    assert result[0]["end_x"] == 60
    assert (
        advanced.structural_pass(
            [event], [], Parameters(team_id=1, attack_positive_x=True)
        )
        == []
    )


def test_temporal_topology_does_not_compare_across_gaps_or_roster_changes():
    base = {
        "period": 1,
        "period_time_ms": 0,
        "players": [
            {"player_id": i, "team_id": 1, "x_m": x, "y_m": y}
            for i, (x, y) in enumerate([(0, 0), (10, 0), (10, 10), (0, 10)])
        ],
    }
    second = {**copy.deepcopy(base), "period_time_ms": 200}
    assert advanced.temporal_topology([base, second], 1, 1000)[0][
        "bottleneck_m"
    ] == pytest.approx(0)
    second["period_time_ms"] = 5000
    assert advanced.temporal_topology([base, second], 1, 1000) == []
    second["period_time_ms"] = 200
    second["players"][0]["player_id"] = 99
    assert advanced.temporal_topology([base, second], 1, 1000) == []


def test_corridor_radius_is_bounded_by_defender_and_pitch():
    frame = {
        "ball": {"x_m": 10, "y_m": 10},
        "players": [
            {"player_id": 1, "team_id": 1, "x_m": 20, "y_m": 10},
            {"player_id": 2, "team_id": 2, "x_m": 15, "y_m": 16},
        ],
    }
    result = advanced.clearance_graph(frame, 1)
    assert result["paths"][0]["bottleneck_radius_m"] == pytest.approx(6)
    assert result["paths"][0]["full_width_m"] == pytest.approx(12)
    frame["ball"] = None
    with pytest.raises(ValueError):
        advanced.clearance_graph(frame, 1)


def test_missing_xg_is_unavailable_and_original_null_survives():
    manifest = one_block("xg_story")
    shot = next(e for e in manifest["evidence"] if e["operation"] == "get_shots")
    shot["response"]["data"]["items"][0]["shot"]["statsbomb_xg"] = None
    spec, blocks = compile_report(manifest)
    assert blocks[0].state == "unavailable" and blocks[0].metrics == {}
    assert (
        next(e for e in spec.evidence if e.operation == "get_shots").response.data[
            "items"
        ][0]["shot"]["statsbomb_xg"]
        is None
    )


def test_replay_keeps_ball_absence_and_renders_original_samples():
    _, blocks = compile_report(one_block("play_replay"))
    assert blocks[0].frames[2]["ball"] is None
    assert len(blocks[0].frames) == 7


def test_unknown_ids_code_and_urls_are_rejected():
    manifest = one_block("shot_map")
    manifest["blocks"][0]["evidence_ids"] = ["unknown"]
    with pytest.raises(ValueError):
        ReportSpec.model_validate(manifest)
    manifest = one_block("shot_map")
    manifest["blocks"][0]["parameters"]["sql"] = "SELECT 1"
    with pytest.raises(ValueError):
        ReportSpec.model_validate(manifest)
    manifest = one_block("shot_map")
    manifest["url"] = "https://invalid.test"
    with pytest.raises(ValueError):
        ReportSpec.model_validate(manifest)


def test_incomplete_pages_and_participant_mismatch_remain_visible():
    manifest = one_block("shot_map")
    shot = next(e for e in manifest["evidence"] if e["operation"] == "get_shots")
    shot["response"]["pagination"]["next_cursor"] = "missing"
    assert compile_report(manifest)[1][0].state == "partial"
    shot["arguments"]["team_id"] = 2
    assert compile_report(manifest)[1][0].state == "incompatible"


def test_self_contained_html_safe_against_script_and_attribute_injection():
    manifest = one_block("shot_map")
    attack = "</script><script>alert(1)</script><img src=x onerror=alert(2)>"
    manifest["title"] = attack
    manifest["evidence"][0]["response"]["warnings"] = [attack]
    result = render_report(manifest)
    assert attack not in result["html"]
    assert "\\u003c/script\\u003e" in result["html"]

    class Inspect(HTMLParser):
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            assert "src" not in attrs
            assert not any(k.startswith("on") for k in attrs)

    Inspect().feed(result["html"])
    assert render_report(manifest)["html"] == result["html"]
    assert "connect-src &#x27;none&#x27;" in result["html"]


def test_original_summary_is_not_summed_for_each_page():
    manifest = one_block("shot_map")
    # Sin filtro visual para poder usar el resumen original completo.
    manifest["blocks"][0]["parameters"] = {}
    shot = next(e for e in manifest["evidence"] if e["operation"] == "get_shots")
    shot["response"]["data"]["summary"] = {"shots": 2}
    extra = copy.deepcopy(shot)
    extra["evidence_id"] = "extra"
    extra["arguments"]["cursor"] = "next"
    extra["response"]["data"]["items"] = []
    shot["response"]["pagination"]["next_cursor"] = "next"
    manifest["evidence"].append(extra)
    manifest["blocks"][0]["evidence_ids"].append("extra")
    block = compile_report(manifest)[1][0]
    assert block.state == "ready" and block.metrics["shots"] == 2


def test_mcp_resolves_host_evidence_and_returns_an_html_resource():
    async def scenario():
        manifest = one_block("shot_map")
        evidence = manifest.pop("evidence")
        async with Client(create_server(evidence)) as client:
            tools = await client.list_tools()
            assert len(tools.tools) == 5
            catalog = await client.call_tool("list_insights", {})
            assert len(catalog.structured_content["insights"]) == 30
            bad = await client.call_tool(
                "render_report", {**manifest, "evidence": evidence}
            )
            assert bad.is_error
            result = await client.call_tool("render_report", manifest)
            assert not result.is_error and "html" not in result.structured_content
            uri = result.structured_content["resource_uri"]
            resource = await client.read_resource(uri)
            assert "<!doctype html>" in resource.contents[0].text
            assert result.structured_content["blocks"][0]["state"] == "ready"

    asyncio.run(scenario())


def test_mcp_render_insight_embeds_only_referenced_evidence_and_match_context():
    async def scenario():
        manifest = one_block("shot_map")
        evidence = manifest.pop("evidence")
        block = manifest["blocks"][0]
        referenced = set(block["evidence_ids"])
        # El contexto del partido aporta nombres y dorsales aunque nadie lo declare.
        context = {
            e["evidence_id"] for e in evidence if e["operation"] == "get_match_context"
        }
        unreferenced = {e["evidence_id"] for e in evidence} - referenced - context
        assert unreferenced and context
        async with Client(create_server(evidence)) as client:
            result = await client.call_tool("render_insight", block)
            assert not result.is_error
            resource = await client.read_resource(
                result.structured_content["resource_uri"]
            )
        html = resource.contents[0].text
        assert all(
            f'id="evidence-{evidence_id}"' in html
            for evidence_id in referenced | context
        )
        assert all(
            f'id="evidence-{evidence_id}"' not in html for evidence_id in unreferenced
        )

    asyncio.run(scenario())


def test_aggregated_values_cannot_be_refiltered_as_another_team():
    manifest = one_block("occupation_heatmap")
    manifest["blocks"][0]["parameters"]["team_id"] = 2
    assert compile_report(manifest)[1][0].state == "incompatible"


def test_heatmaps_share_scales_but_do_not_mix_units():
    manifest = one_block("occupation_heatmap")
    block = copy.deepcopy(manifest["blocks"][0])
    block["id"] = "second"
    manifest["blocks"].append(block)
    _, blocks = compile_report(manifest)
    assert blocks[0].unit == "s·jugador"
    assert (
        blocks[0].metrics["heatmap_scale_max"]
        == blocks[1].metrics["heatmap_scale_max"]
        == 4
    )


def test_xg_series_adapter_accumulates_only_non_missing_values():
    manifest = one_block("xg_story")
    series = next(
        e for e in manifest["evidence"] if e["operation"] == "get_metric_series"
    )
    manifest["blocks"][0]["evidence_ids"] = [series["evidence_id"]]
    series["response"]["data"]["series"] = [
        {"period": 1, "start_ms": 0, "end_ms": 1000, "metrics": {"xg": 0.2}},
        {"period": 1, "start_ms": 1000, "end_ms": 2000, "metrics": {"xg": 0.3}},
    ]
    assert compile_report(manifest)[1][0].metrics["observed_xg"] == pytest.approx(0.5)
    series["response"]["data"]["series"][1]["metrics"]["xg"] = None
    b = compile_report(manifest)[1][0]
    assert b.state == "unavailable" and not b.series


def test_team_palette_and_player_identity_shared_without_mutating_evidence():
    manifest = demo_manifest()
    original = copy.deepcopy(manifest["evidence"])
    manifest["teams"] = [{"team_id": 1, "color": "#123456", "name": "Equipo Azul"}]
    spec, blocks = compile_report(manifest)
    assert all(b.teams["1"]["color"] == "#123456" for b in blocks)
    assert spec.model_dump()["evidence"] == original
    html = render_report(manifest)["html"]
    assert '"color": "#123456"' in html and "Report colours" in html
    manifest["teams"][0]["color"] = "#fff; background:url(https://invalid.test)"
    with pytest.raises(ValueError):
        ReportSpec.model_validate(manifest)


def test_heatmap_sums_players_in_same_cell_and_preserves_raw_rows():
    manifest = one_block("occupation_heatmap")
    heat = next(e for e in manifest["evidence"] if e["operation"] == "get_heatmap")
    heat["response"]["data"]["cells"] = [
        {"player_id": 103, "cell_x_m": 10, "cell_y_m": 20, "seconds_in_zone": 3},
        {"player_id": 104, "cell_x_m": 10, "cell_y_m": 20, "seconds_in_zone": 4},
    ]
    block = compile_report(manifest)[1][0]
    assert len(block.polygons) == 1 and block.polygons[0]["value"] == 7
    assert len(block.rows) == 2 and block.metrics["heatmap_scale_max"] == 7


def test_voronoi_keeps_team_identity_and_only_overlays_matching_tracking():
    manifest = one_block("space_partition")
    block_spec = manifest["blocks"][0]
    block_spec["parameters"] = {"period": 1, "time_ms": 10000}
    tracking = next(
        e for e in manifest["evidence"] if e["operation"] == "get_tracking_window"
    )
    block_spec["evidence_ids"].append(tracking["evidence_id"])
    block = compile_report(manifest)[1][0]
    assert {p["team_id"] for p in block.polygons} == {1, 2}
    assert {p["team_id"] for p in block.points} == {1, 2}
    assert len(block.points) == 14
    tracking["response"]["data"]["frames"] = []
    block = compile_report(manifest)[1][0]
    assert not block.points  # Polygon centroids never become player positions.


def test_passing_network_uses_matching_actions_for_positions_and_falls_back_honestly():
    manifest = one_block("passing_network")
    net = next(
        e for e in manifest["evidence"] if e["operation"] == "get_passing_network"
    )
    passes = next(e for e in manifest["evidence"] if e["operation"] == "get_passes")
    manifest["blocks"][0]["evidence_ids"].append(passes["evidence_id"])
    passes["arguments"] = copy.deepcopy(net["arguments"])
    passes["response"]["data"]["items"] = [
        {
            "event_id": "a",
            "period": 1,
            "period_time_ms": 10000,
            "team_id": 1,
            "player_id": 101,
            "location_x": 12,
            "location_y": 8,
            "pass": {
                "recipient_player_id": 103,
                "end_x": 60,
                "end_y": 40,
                "outcome": None,
            },
        },
        {
            "event_id": "b",
            "period": 1,
            "period_time_ms": 11000,
            "team_id": 1,
            "player_id": 103,
            "location_x": 60,
            "location_y": 40,
            "pass": {
                "recipient_player_id": 105,
                "end_x": 96,
                "end_y": 64,
                "outcome": None,
            },
        },
    ]
    block = compile_report(manifest)[1][0]
    assert block.layout == "pitch"
    assert next(p for p in block.points if p["id"] == 101)["x"] == pytest.approx(10.5)
    assert next(p for p in block.points if p["id"] == 105)["y"] == pytest.approx(54.4)
    passes["arguments"]["scope"] = {"kind": "period", "period": 2}
    block = compile_report(manifest)[1][0]
    assert block.layout == "schematic"
    assert "Red esquemática" in render_report(manifest)["html"]


def test_svg_marker_ids_are_unique_and_visual_selection_remains_parametric():
    manifest = one_block("pass_map")
    manifest["blocks"][0]["visual"] = {"span": "full", "show_labels": False}
    html = render_report(manifest)["html"]

    class IDs(HTMLParser):
        def __init__(self):
            super().__init__()
            self.ids = []

        def handle_starttag(self, tag, attrs):
            if key := dict(attrs).get("id"):
                self.ids.append(key)

    parser = IDs()
    parser.feed(html)
    assert len(set(parser.ids)) == len(parser.ids)
    assert 'data-span="full"' in html


def test_possession_graph_labels_recorded_spans_without_claiming_official_share():
    manifest = one_block("sequence_explorer")
    possession = next(
        e for e in manifest["evidence"] if e["operation"] == "get_possessions"
    )
    manifest["blocks"][0]["evidence_ids"] = [possession["evidence_id"]]
    possession["response"]["data"]["items"] = [
        {
            "period": 1,
            "team_id": 1,
            "start_ms": 1000,
            "end_ms": 5000,
            "passes": 3,
            "shots": 0,
            "event_ids": ["a", "b"],
        },
        {
            "period": 2,
            "team_id": 2,
            "start_ms": 2000,
            "end_ms": 8000,
            "passes": 2,
            "shots": 1,
            "event_ids": ["c", "d"],
        },
    ]
    html = render_report(manifest)["html"]
    assert "not an official possession percentage" in html and "recorded sequence" in html
    assert 'aria-label="Recorded possession sequences"' in html


def test_network_display_threshold_only_changes_visible_edges_not_metrics():
    manifest = one_block("passing_network")
    manifest["blocks"][0]["visual"] = {"min_edge_weight": 4}
    spec, blocks = compile_report(manifest)
    assert len(blocks[0].vectors) == 3
    html = render_report(spec)["html"]
    assert "Visible links have weight ≥ 4" in html
    assert 'marker-end="url(' not in html  # All fixture edges weigh 3.


def test_geometric_line_breaks_bind_original_pass_ids_without_inventing_tags():
    manifest = one_block("defensive_geometry")
    evidence = next(
        e for e in manifest["evidence"] if e["operation"] == "get_defensive_profile"
    )
    evidence["operation"] = evidence["response"]["operation_id"] = "get_line_breaks"
    evidence["response"]["data"] = {
        "samples": [
            {
                "event_id": "fixture-1",
                "period": 1,
                "time_ms": 11000,
                "lines_crossed": [{"line": "midfield", "reference_x_m": 50}],
            }
        ]
    }
    passes = next(e for e in manifest["evidence"] if e["operation"] == "get_passes")
    manifest["blocks"][0].update(
        evidence_ids=[evidence["evidence_id"], passes["evidence_id"]],
        parameters={"team_id": 1, "period": 1},
    )
    block = compile_report(manifest)[1][0]
    assert block.metrics == {"observed_line_breaks": 1, "mapped_line_breaks": 1}
    assert (
        len(block.vectors) == 1 and block.coordinate_reference == "acting_team_attack"
    )
    assert "through_ball" not in block.vectors[0]
    assert "no equivale a la etiqueta through_ball" in render_report(manifest)["html"]


def test_mcp_agent_can_discover_and_render_each_piece_and_compose_a_page():
    """Agent protocol flow, using parameters/IDs instead of generated HTML."""

    async def scenario():
        manifest = demo_manifest()
        async with Client(create_server(manifest["evidence"])) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            assert set(tools) == {
                "list_insights",
                "describe_insight",
                "validate_report",
                "render_insight",
                "render_report",
            }
            schema = tools["render_insight"].input_schema
            assert set(schema["properties"]["insight_id"]["enum"]) == set(RECIPES)
            assert schema["additionalProperties"] is False
            catalog = (await client.call_tool("list_insights", {})).structured_content
            assert {e["evidence_id"] for e in catalog["evidence_catalog"]} == {
                e["evidence_id"] for e in manifest["evidence"]
            }
            described = (
                await client.call_tool(
                    "describe_insight", {"insight_id": "passing_network"}
                )
            ).structured_content
            assert described["block_schema"] and described["visual_schema"]
            for block in manifest["blocks"]:
                result = await client.call_tool(
                    "render_insight",
                    {**block, "teams": [{"team_id": 1, "color": "#123456"}]},
                )
                assert not result.is_error, block["insight_id"]
                assert len(result.structured_content["blocks"]) == 1
                assert result.structured_content["blocks"][0]["state"] == "ready"
                html = (
                    (
                        await client.read_resource(
                            result.structured_content["resource_uri"]
                        )
                    )
                    .contents[0]
                    .text
                )
                assert html.startswith("<!doctype html>") and "#123456" in html
            plan = {k: v for k, v in manifest.items() if k != "evidence"}
            plan["blocks"] = plan["blocks"][:3]
            checked = (
                await client.call_tool("validate_report", plan)
            ).structured_content
            assert checked["valid"] and checked["ready"]
            composed = (
                await client.call_tool("render_report", plan)
            ).structured_content
            assert len(composed["blocks"]) == 3
            html = (
                (await client.read_resource(composed["resource_uri"])).contents[0].text
            )
            assert html.count('<section class="insight"') == 3
            assert len((await client.list_resources()).resources) <= 4
            bad = await client.call_tool(
                "render_insight",
                {"insight_id": "shot_map", "evidence_ids": ["not-authorized"]},
            )
            assert bad.is_error
            bad = await client.call_tool(
                "render_insight",
                {
                    "insight_id": "shot_map",
                    "evidence_ids": [manifest["evidence"][0]["evidence_id"]],
                    "html": "<script>",
                },
            )
            assert bad.is_error

    asyncio.run(scenario())


def test_mcp_valid_plan_does_not_claim_missing_data_ready():
    async def scenario():
        manifest = one_block("xg_story")
        for evidence in manifest["evidence"]:
            if evidence["operation"] == "get_shots":
                for event in evidence["response"]["data"]["items"]:
                    event["shot"]["statsbomb_xg"] = None
        async with Client(create_server(manifest.pop("evidence"))) as client:
            result = (
                await client.call_tool("validate_report", manifest)
            ).structured_content
            assert result["valid"] and not result["ready"]
            assert result["blocks"][0]["state"] == "unavailable"

    asyncio.run(scenario())


def test_report_parts_are_the_same_organisms_as_the_exported_page():
    from inside_game.insights.pages import report_parts

    manifest = demo_manifest()
    html = render_report(manifest)["html"]
    parts = report_parts(manifest)
    # La web compone su lienzo con estas piezas: deben ser idénticas a la exportación.
    assert f"<header>{parts['header']}</header>" in html
    assert f'<main class="report {parts["template_id"]}">{parts["main"]}</main>' in html
    assert parts["payload_json"] in html
    assert (
        html.count('<section class="insight"')
        == parts["main"].count('<section class="insight"')
        == 30
    )


def test_structural_pass_says_when_the_scope_has_no_completed_passes():
    import copy

    from inside_game.insights.demo import demo_manifest
    from inside_game.insights.pages import compile_report

    manifest = demo_manifest()
    evidence = copy.deepcopy(
        [e for e in manifest["evidence"] if e["evidence_id"] in {"e5", "e1"}]
    )
    next(e for e in evidence if e["evidence_id"] == "e5")["response"]["data"][
        "items"
    ] = []
    block = next(b for b in manifest["blocks"] if b["id"] == "structural_pass")
    _, [compiled] = compile_report(
        {"title": "Sin pases", "blocks": [block], "evidence": evidence}
    )
    assert compiled.state == "unavailable"
    assert any("No hay pases completados" in w for w in compiled.warnings)


def test_metrics_drop_missing_values_and_unknown_categories():
    from inside_game.insights.adapters import meaningful_metrics

    metrics = {
        "q5.shots": 21,
        "q5.goals": None,
        "q5.xg": None,
        "q5.outcomes.Unknown (source shot outcome unavailable)": 21,
        "q5.body_parts.Unknown": 20,
        "q5.body_parts.Head": 1,
        "q5.shots_unknown_total": 0,
    }
    assert meaningful_metrics(metrics) == {
        "q5.shots": 21,
        "q5.body_parts.Head": 1,
        "q5.shots_unknown_total": 0,
    }


def test_shot_tooltip_omits_unknown_outcome_and_missing_xg():
    import copy
    import re

    from inside_game.insights.demo import demo_manifest
    from inside_game.insights.pages import render_report

    manifest = demo_manifest()
    block = next(b for b in manifest["blocks"] if b["insight_id"] == "shot_map")
    evidence = copy.deepcopy(manifest["evidence"])
    for e in evidence:
        for item in e["response"]["data"].get("items", []):
            shot = item.get("shot")
            if shot:
                shot["statsbomb_xg"] = None
                shot["outcome"] = {"name": "Unknown (source shot outcome unavailable)"}
    request = {"title": "Tooltip", "blocks": [block], "evidence": evidence}
    html = render_report(request)["html"]
    tooltips = re.findall(r"<title>([^<]*)</title>", html)
    shot_tooltips = [t for t in tooltips if " · P" in t]
    assert shot_tooltips
    assert not any("Unknown" in t or "xG" in t for t in shot_tooltips)


def test_match_timeline_graphs_event_activity_per_team_not_only_shots():
    from inside_game.insights.adapters import ACTIVITY_BIN_MS
    from inside_game.insights.demo import demo_manifest
    from inside_game.insights.pages import compile_report

    manifest = demo_manifest()
    block = next(b for b in manifest["blocks"] if b["id"] == "match_timeline")
    ids = set(block["evidence_ids"])
    evidence = [e for e in manifest["evidence"] if e["evidence_id"] in ids]
    _, [compiled] = compile_report(
        {"title": "Cronología", "blocks": [block], "evidence": evidence}
    )
    wanted = block["parameters"]
    events = [
        item
        for e in evidence
        if e["operation"] == "get_events"
        for item in e["response"]["data"]["items"]
        if item.get("team_id") == wanted["team_id"]
        and item.get("period") == wanted["period"]
    ]
    assert compiled.series, "la cronología debe tener serie de actividad"
    assert {s["team_id"] for s in compiled.series} == {wanted["team_id"]}
    assert sum(s["value"] for s in compiled.series) == len(events) > 0
    assert all(s["time_ms"] % ACTIVITY_BIN_MS == 0 for s in compiled.series)
    assert not any(s["group"] == "shots" for s in compiled.series)


def test_match_timeline_lists_goals_substitutions_and_cards_without_duplicates():
    import copy

    from inside_game.insights.demo import demo_manifest
    from inside_game.insights.pages import compile_report

    manifest = demo_manifest()
    block = copy.deepcopy(
        next(b for b in manifest["blocks"] if b["id"] == "match_timeline")
    )
    block["parameters"].pop("team_id")
    block["parameters"].pop("period")
    block["parameters"].pop("time_ms")
    base = next(e for e in manifest["evidence"] if e["operation"] == "get_events")

    def evidence(evidence_id, operation, data):
        item = copy.deepcopy(base)
        item["evidence_id"], item["operation"] = evidence_id, operation
        item["response"]["operation_id"] = operation
        item["response"]["data"] = data
        return item

    def event(event_id, team_id, period_time_ms, **extra):
        return {
            "event_id": event_id,
            "period": 1,
            "period_time_ms": period_time_ms,
            "team_id": team_id,
            "player_id": 103,
            **extra,
        }

    goal = event("g1", 1, 600000, shot={"outcome": {"name": "Goal"}})
    miss = event("s1", 1, 700000, shot={"outcome": {"name": "Saved"}})
    sub = event("c1", 2, 1200000)
    card = event(
        "k1",
        2,
        1300000,
        details={"foul_committed": {"card": {"name": "Yellow Card"}}},
    )
    evidence_list = [
        evidence("m1", "get_events", {"items": [goal, miss], "total": 2}),
        evidence("m2", "get_substitutions", {"items": [sub, sub], "total": 2}),
        evidence("m3", "get_discipline", {"items": [], "cards": [card]}),
    ]
    block["evidence_ids"] = ["m1", "m2", "m3"]
    _, [compiled] = compile_report(
        {"title": "Cronología", "blocks": [block], "evidence": evidence_list}
    )
    assert [(m["kind"], m["time_ms"]) for m in compiled.markers] == [
        ("goal", 600000),
        ("substitution", 1200000),
        ("card", 1300000),
    ]
    assert compiled.markers[2]["label"] == "Yellow card"


def test_timeline_chart_draws_markers_in_team_lanes_with_tooltips():
    from inside_game.insights.charts import series
    from inside_game.insights.contracts import BlockData

    block = BlockData(
        id="match_timeline",
        insight_id="match_timeline",
        title="Cronología",
        method_id="visual_match_timeline_v1",
        evidence_ids=["e1"],
        series=[
            {"period": 1, "time_ms": 0, "value": 3, "group": "events:1", "team_id": 1},
            {
                "period": 1,
                "time_ms": 300000,
                "value": 5,
                "group": "events:1",
                "team_id": 1,
            },
        ],
        markers=[
            {
                "kind": "goal",
                "label": None,
                "period": 1,
                "time_ms": 600000,
                "team_id": 1,
            },
            {
                "kind": "card",
                "label": "Tarjeta roja",
                "period": 1,
                "time_ms": 900000,
                "team_id": 2,
            },
            {
                "kind": "substitution",
                "label": None,
                "period": 2,
                "time_ms": 100000,
                "team_id": 1,
            },
        ],
        teams={
            "1": {"name": "Home", "color": "#2463bc"},
            "2": {"name": "Visita", "color": "#bf402e"},
        },
    )
    html = series(block)
    assert "P1 10′ · Goal · Home" in html and "P1 15′ · Tarjeta roja · Visita" in html
    assert "Substitution" not in html  # el período 2 no tiene serie: sólo lo muestra la lista
    assert "#c0392b" in html  # tarjeta roja
    assert 'viewBox="0 0 690 258"' in html
    # el eje se extiende hasta el último marcador para que no se salga del gráfico
    assert "15.0′" in html


@pytest.mark.parametrize(
    "team_id,period,expected", [(None, 1, 0.2), (1, None, 0.2), (1, 2, 0.1)]
)
def test_shot_map_summary_matches_filtered_unique_shots(team_id, period, expected):
    manifest = one_block("shot_map")
    manifest["blocks"][0]["parameters"] = {"team_id": team_id, "period": period}
    evidence = next(e for e in manifest["evidence"] if e["operation"] == "get_shots")
    first = copy.deepcopy(evidence["response"]["data"]["items"][0])
    first.update(period=1, team_id=1)
    first["shot"]["statsbomb_xg"] = 0.2
    second = copy.deepcopy(first)
    second.update(event_id="second-period", period=2)
    second["shot"]["statsbomb_xg"] = 0.1
    evidence["response"]["data"]["items"] = [first, second]
    evidence["response"]["data"]["summary"] = {"shots": 2, "xg": 0.3}
    if team_id == 1 and period is None:
        second["team_id"] = 2
    # A second view of the same events must never count them again.
    duplicate = copy.deepcopy(evidence)
    duplicate.update(evidence_id="duplicate", query_id="other-view")
    manifest["evidence"].append(duplicate)
    manifest["blocks"][0]["evidence_ids"].append("duplicate")
    block = compile_report(manifest)[1][0]
    assert block.state == "ready"
    assert block.metrics["shots"] == len(block.points) == 1
    assert block.metrics["xg"] == pytest.approx(expected)


def test_partial_xg_does_not_masquerade_as_team_total():
    manifest = one_block("shot_map")
    manifest["blocks"][0]["parameters"] = {}
    evidence = next(e for e in manifest["evidence"] if e["operation"] == "get_shots")
    rows = evidence["response"]["data"]["items"]
    rows[1]["team_id"] = rows[0]["team_id"]
    rows[1]["shot"]["statsbomb_xg"] = None
    block = compile_report(manifest)[1][0]
    assert "xg" not in block.metrics
    assert not any("xg" in row for row in block.by_team.values())


def test_xg_bins_are_ordered_deduplicated_and_period_filtered():
    manifest = one_block("xg_story")
    series = next(
        e for e in manifest["evidence"] if e["operation"] == "get_metric_series"
    )
    manifest["blocks"][0]["evidence_ids"] = [series["evidence_id"]]
    manifest["blocks"][0]["parameters"] = {"team_id": 1, "period": 1}
    series["response"]["data"]["series"] = [
        {"period": 2, "start_ms": 0, "end_ms": 1000, "metrics": {"xg": 0.8}},
        {"period": 1, "start_ms": 1000, "end_ms": 2000, "metrics": {"xg": 0.3}},
        {"period": 1, "start_ms": 0, "end_ms": 1000, "metrics": {"xg": 0.2}},
    ]
    duplicate = copy.deepcopy(series)
    duplicate.update(evidence_id="repeated-series", query_id="another-query")
    manifest["evidence"].append(duplicate)
    manifest["blocks"][0]["evidence_ids"].append("repeated-series")
    block = compile_report(manifest)[1][0]
    assert block.state == "ready"
    assert [row["value"] for row in block.series] == pytest.approx([0.2, 0.5])
    assert block.metrics["observed_xg"] == pytest.approx(0.5)
    series["response"]["data"]["series"][1]["start_ms"] = 500
    manifest["blocks"][0]["evidence_ids"] = [series["evidence_id"]]
    assert compile_report(manifest)[1][0].state == "unavailable"


def test_xg_probability_range_and_period_reset_are_explicit():
    manifest = one_block("xg_story")
    manifest["blocks"][0]["parameters"] = {}
    evidence = next(e for e in manifest["evidence"] if e["operation"] == "get_shots")
    rows = evidence["response"]["data"]["items"]
    rows[0]["shot"]["statsbomb_xg"] = 0.2
    rows[1]["shot"]["statsbomb_xg"] = 0.3
    rows[1].update(period=2, team_id=rows[0]["team_id"])
    block = compile_report(manifest)[1][0]
    assert [row["value"] for row in block.series] == pytest.approx([0.2, 0.3])
    assert block.metrics["observed_xg"] == pytest.approx(0.5)
    assert "each period starts at zero" in render_report(manifest)["html"]
    rows[1]["shot"]["statsbomb_xg"] = 1.01
    assert compile_report(manifest)[1][0].state == "unavailable"
