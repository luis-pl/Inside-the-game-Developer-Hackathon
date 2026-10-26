"""Una conversación sobre el mismo partido acumula piezas en un solo informe."""

import copy
import re

from test_insights_web_build import FIXTURE, web

from inside_game.agents.insights_agent.merge import match_of, merge_manifests
from inside_game.insights.pages import compile_report, render_report

CONTEXT = copy.deepcopy(FIXTURE["get_match_context"])


def evidence(evidence_id, operation, match_id=900001):
    item = {
        "evidence_id": evidence_id,
        "query_id": evidence_id.split("-")[0],
        "operation": operation,
        "arguments": {"match_id": match_id},
        "response": copy.deepcopy(FIXTURE[operation]),
    }
    if operation == "get_match_context":
        item["response"]["data"] = {
            "match": {
                "match_id": match_id,
                "home_team_id": 1,
                "away_team_id": 2,
                "home_team_name": "Local",
                "away_team_name": "Visita",
            },
            "lineups": [],
            "position_intervals": [],
            "periods": [],
        }
    return item


def manifest(block_id, insight_id, operation, match_id=900001, **block):
    # Los IDs de evidencia se repiten entre peticiones: así llegan del agente.
    return {
        "title": block_id,
        "template_id": "custom_report",
        "blocks": [
            {
                "id": block_id,
                "insight_id": insight_id,
                "title": block.pop("title", block_id),
                "evidence_ids": ["q2-p1"],
                "parameters": block.pop("parameters", {}),
            }
        ],
        "teams": [],
        "evidence": [
            evidence("q1-p1", "get_match_context", match_id),
            evidence("q2-p1", operation, match_id),
        ],
    }


SHOTS = manifest("shots", "shot_map", "get_shots", title="Mapa de tiros")
PASSES = manifest("passes", "pass_map", "get_passes", title="Mapa de pases")


def test_new_pieces_are_added_with_unique_evidence_and_one_context():
    merged, added = merge_manifests(SHOTS, PASSES, 2)
    assert added == 1
    assert [b["id"] for b in merged["blocks"]] == ["passes", "shots"], (
        "lo nuevo, arriba"
    )
    ids = [e["evidence_id"] for e in merged["evidence"]]
    assert len(set(ids)) == len(ids)
    assert sorted(ids) == ["q1-p1", "q2-p1", "t2-q2-p1"]
    assert [b["evidence_ids"] for b in merged["blocks"]] == [["t2-q2-p1"], ["q2-p1"]]
    assert sum(e["operation"] == "get_match_context" for e in merged["evidence"]) == 1
    assert merged["template_id"] == "custom_report"


def test_inputs_are_not_modified_and_the_merge_compiles_and_renders():
    before = copy.deepcopy([SHOTS, PASSES])
    merged, _ = merge_manifests(SHOTS, PASSES, 2)
    assert [SHOTS, PASSES] == before
    _, blocks = compile_report(merged)
    assert [b.insight_id for b in blocks] == ["pass_map", "shot_map"]
    html = render_report(merged)["html"]
    assert html.count('<section class="insight"') == 2


def test_a_different_match_or_a_missing_context_does_not_merge():
    other_match = manifest("passes", "pass_map", "get_passes", match_id=900002)
    assert match_of(SHOTS) == (900001, 1, 2)
    assert merge_manifests(SHOTS, other_match, 2) is None
    no_context = copy.deepcopy(PASSES)
    no_context["evidence"] = [
        e for e in no_context["evidence"] if e["evidence_id"] != "q1-p1"
    ]
    assert merge_manifests(SHOTS, no_context, 2) is None
    assert merge_manifests(None, PASSES, 2) is None


def test_a_piece_already_shown_is_not_repeated():
    again = copy.deepcopy(SHOTS)
    merged, added = merge_manifests(SHOTS, again, 2)
    assert added == 0 and len(merged["blocks"]) == 1
    assert [e["evidence_id"] for e in merged["evidence"]] == ["q1-p1", "q2-p1"]


def test_same_recipe_with_other_parameters_is_kept_with_a_distinct_title_and_id():
    second_half = manifest(
        "shots",
        "shot_map",
        "get_shots",
        title="Mapa de tiros",
        parameters={"period": 2},
    )
    merged, added = merge_manifests(SHOTS, second_half, 2)
    assert added == 1
    ids = [b["id"] for b in merged["blocks"]]
    titles = [b["title"] for b in merged["blocks"]]
    assert len(set(ids)) == 2 and ids[1] == "shots" and ids[0].startswith("shots-")
    assert titles == ["Mapa de tiros · 2.ª parte", "Mapa de tiros"]
    assert merged["blocks"][0]["evidence_ids"] == ["t2-q2-p1"]


def test_references_to_unknown_evidence_make_the_merge_decline():
    broken = copy.deepcopy(PASSES)
    broken["blocks"][0]["evidence_ids"] = ["q9-p9"]
    assert merge_manifests(SHOTS, broken, 2) is None


def ask(client, intent, append_to=None):
    body = {"intent": intent}
    if append_to:
        body["append_to"] = append_to
    response = client.post("/api/ask", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def custom(*insight_ids):
    return {
        "template_id": "custom_report",
        "match_id": 900001,
        "insight_ids": list(insight_ids),
    }


def headings(data):
    return re.findall(r"<h2>([^<]*)</h2>", data["canvas_html"])


def test_web_accumulates_what_a_continuous_conversation_asks_for():
    with web() as client:
        first = ask(client, custom("shot_map"))
        assert first["merged"] is False
        second = ask(client, custom("pass_map"), append_to=first["report_id"])
        assert second["merged"] is True
        assert second["report_id"] != first["report_id"]
        titles = [h for h in headings(second) if "Mapa" in h]
        assert titles[1] == "Mapa de tiros" and titles[0].startswith("Mapa de pases")
        assert len(titles) == 2
        assert "ahora tiene 2 piezas" in second["message_html"]
        assert "2 piezas" in second["title"]
        # El informe exportado lleva las dos piezas; el primero sigue como estaba.
        exported = client.get(second["report_url"]).text
        assert exported.count('<section class="insight"') == 2
        again = client.get(f"/api/reports/{first['report_id']}").json()
        assert again["canvas_html"] == first["canvas_html"]


def test_web_replaces_the_report_when_the_conversation_is_new_or_the_id_is_unknown():
    with web() as client:
        first = ask(client, custom("shot_map"))
        fresh = ask(client, custom("pass_map"))  # «Nueva conversación»: sin append_to
        assert fresh["merged"] is False and "Mapa de tiros" not in headings(fresh)
        unknown = ask(client, custom("pass_map"), append_to="0" * 32)
        assert unknown["merged"] is False and "Mapa de tiros" not in headings(unknown)
        assert first["report_id"] not in {fresh["report_id"], unknown["report_id"]}


def test_web_does_not_repeat_a_piece_that_is_already_in_the_report():
    with web() as client:
        first = ask(client, custom("shot_map"))
        again = ask(client, custom("shot_map"), append_to=first["report_id"])
        assert again["merged"] is True
        assert headings(again).count("Mapa de tiros") == 1
        assert "ya estaba en el informe" in again["message_html"]


def test_only_the_latest_reports_keep_their_evidence_in_memory():
    from inside_game.agents.insights_agent.web import KEEP_MANIFESTS, Reports

    reports = Reports(limit=10)
    ids = [reports.add({"manifest": {"evidence": [1]}, "html": "x"}) for _ in range(6)]
    kept = [i for i in ids if "manifest" in reports.items[i]]
    assert kept == ids[-KEEP_MANIFESTS:]
    assert all(reports.items[i]["html"] == "x" for i in ids), "el HTML se conserva"


def test_the_client_script_sends_the_current_report_and_clears_it_on_reset():
    from inside_game.insights.templates import WORKSPACE_JS

    assert "append_to:state.current" in WORKSPACE_JS
    assert "state.current=data.report_id" in WORKSPACE_JS
    assert "state.previous=null;state.current=null" in WORKSPACE_JS
