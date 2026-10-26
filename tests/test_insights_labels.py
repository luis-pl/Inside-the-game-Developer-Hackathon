"""Etiquetas legibles, datos por equipo y cifras que no engañan, sin red ni LLM."""

import copy

from inside_game.agents.insights_agent.profiles import unannotated_by_source
from inside_game.insights.adapters import meaningful_metrics, team_breakdown
from inside_game.insights.contracts import BlockData, Parameters
from inside_game.insights.labels import column_label, metric_label
from inside_game.insights.molecules import data_table, metric_reading
from inside_game.insights.molecules import team_breakdown as breakdown_table
from inside_game.insights.organisms import comparison_bars

TEAMS = {
    "1": {"name": "Local", "color": "#2463bc"},
    "2": {"name": "Visita", "color": "#bf402e"},
}


def test_metric_labels_are_spanish_and_drop_internal_prefixes():
    assert metric_label("q15.tackles_won") == "Entradas ganadas"
    assert metric_label("a1-q3.aggregate.shots") == "Tiros"
    assert metric_label("summary.interceptions") == "Intercepciones"
    assert metric_label("q5.outcomes.Off T") == "Resultado: Fuera"
    assert metric_label("q5.body_parts.Left Foot") == "Parte del cuerpo: Pie izquierdo"
    assert metric_label("event_counts.Ball Recovery") == "Eventos · Recuperaciones"
    assert metric_label("team_area_m2.2", TEAMS) == "Área de Visita (m²)"
    assert metric_label("baseline.component_count") == "Referencia: Componentes"
    assert metric_label("clave_nueva_sin_traducir") == "clave nueva sin traducir"


def test_lanes_do_not_claim_a_side_the_sources_do_not_define():
    assert metric_label("channel_1") == "Carril 1 (banda)"
    assert metric_label("channel_3") == "Carril 3 (centro)"
    assert metric_label("channel_5") == "Carril 5 (banda)"
    text = " ".join(metric_label(f"channel_{n}") for n in range(1, 6))
    assert "izquierda" not in text and "derecha" not in text


def test_table_headers_and_rates_read_naturally():
    html = data_table([{"event_id": "e1", "time_ms": 1000, "player": "Ana", "x": 3}])
    assert "ID del evento" in html and "Tiempo (ms)" in html and "x (m)" in html
    assert "event_id" not in html and "time_ms" not in html
    assert column_label("tackles_won") == "Entradas ganadas"
    assert "62.5%" in metric_reading("q1.completion_rate", 0.625)


def test_metrics_drop_pagination_total_and_unannotated_zeros_but_keep_real_values():
    metrics = {"q1.total": 0, "q1.tackles_won": 0, "q1.interceptions": 12, "q1.xg": 0}
    kept = meaningful_metrics(metrics, {"tackles_won", "interceptions", "xg"})
    assert kept == {"q1.interceptions": 12}, "un valor distinto de cero se conserva"
    assert meaningful_metrics({"q1.tackles_won": 0}) == {"q1.tackles_won": 0}, (
        "sin perfil, un cero sigue siendo un cero"
    )


def shot(team_id, outcome="Goal", xg=None):
    return {
        "team_id": team_id,
        "shot": {"outcome": {"name": outcome}, "statsbomb_xg": xg},
    }


def test_shot_breakdown_separates_teams_and_hides_what_the_source_lacks():
    events = [shot(1), shot(1, "Saved"), shot(2, "Off T")]
    rows = team_breakdown("shot_map", events, Parameters())
    assert rows == {
        "1": {"shots": 2, "goals": 1, "shots_on_target": 2},
        "2": {"shots": 1, "goals": 0, "shots_on_target": 0},
    }
    unknown = [shot(1, "Unknown (source shot outcome unavailable)"), shot(2, "Unknown")]
    assert team_breakdown("shot_map", unknown, Parameters()) == {
        "1": {"shots": 1},
        "2": {"shots": 1},
    }
    with_xg = [shot(1, "Saved", 0.25), shot(1, "Goal", 0.5), shot(2, "Saved", 0.1)]
    assert team_breakdown("shot_map", with_xg, Parameters())["1"]["xg"] == 0.75


def test_breakdown_is_only_for_whole_match_pieces_with_two_teams():
    events = [shot(1), shot(2)]
    assert team_breakdown("shot_map", events, Parameters(team_id=1)) == {}
    assert team_breakdown("shot_map", events[:1], Parameters()) == {}


def test_defensive_breakdown_keeps_only_busy_columns_and_drops_unannotated_ones():
    def action(team_id, kind):
        return {"team_id": team_id, "type_name": kind}

    events = (
        [action(1, "Interception")] * 5
        + [action(2, "Interception")] * 3
        + [action(1, "Pressure")] * 2
    )
    rows = team_breakdown("defensive_actions", events, Parameters())
    assert rows["1"] == {"event_counts.Interception": 5, "event_counts.Pressure": 2}
    assert "event_counts.Clearance" not in rows["1"], "sin ninguna: no se muestra"
    hidden = team_breakdown(
        "defensive_actions", events, Parameters(), {"event_counts.Pressure"}
    )
    assert "event_counts.Pressure" not in hidden["1"]


def test_breakdown_table_names_each_team_with_its_color():
    html = breakdown_table(
        {"1": {"shots": 2, "completion_rate": 0.5}, "2": {"shots": 1}}, TEAMS
    )
    assert "<th>Tiros</th>" in html and "<th>Acierto de pase</th>" in html
    assert "Local" in html and "Visita" in html and "#2463bc" in html
    assert "50.0%" in html
    assert breakdown_table({}, TEAMS) == ""


def test_comparison_names_teams_and_metrics_instead_of_ids_and_keys():
    block = BlockData(
        id="c",
        insight_id="entity_comparison",
        title="Comparación",
        method_id="visual_entity_comparison_v1",
        evidence_ids=["e1"],
        teams=copy.deepcopy(TEAMS),
        rows=[
            {"entity_id": 1, "metrics": {"aggregate": {"shots": 5, "goals": 7}}},
            {"entity_id": 2, "metrics": {"aggregate": {"shots": 3, "goals": 4}}},
        ],
    )
    html = comparison_bars(block)
    assert "Local" in html and "Visita" in html
    assert "Tiros" in html and "Goles" in html
    assert "aggregate" not in html
    assert ">1<" not in html and ">2<" not in html, "ids como etiqueta"


def report(source, shots_zero, matches=2):
    def match(match_id):
        metrics = {"q1.shots": 5, "q1.goals": 0 if shots_zero else 2}
        return {
            "match_id": match_id,
            "provider": source,
            "is_synthetic": False,
            "insights": {
                "shot_map": {"state": "ready", "metrics": metrics, "items": {}},
                "hodge_flow": {
                    "state": "ready",
                    "metrics": {"q2.reconstruction_error": 0},
                    "items": {},
                },
            },
        }

    return {"matches": [match(900000 + n) for n in range(matches)]}


def test_unannotated_metrics_need_zero_in_every_measured_match_of_event_recipes():
    found = unannotated_by_source(report("SkillCorner", shots_zero=True))
    assert found == {"SkillCorner": {"shot_map": ["goals"]}}, (
        "sólo recetas de eventos; un error numérico en cero no es «no anotado»"
    )
    assert unannotated_by_source(report("SkillCorner", shots_zero=False)) == {
        "SkillCorner": {}
    }
    assert unannotated_by_source(report("SkillCorner", True, matches=1)) == {
        "SkillCorner": {}
    }, "con un solo partido no se distingue de un cero real"


def pass_event(x, y, end_x, end_y, outcome=None):
    return {
        "attacking_x_m": x,
        "attacking_y_m": y,
        "pass": {"end_x": end_x, "end_y": end_y, "outcome": outcome},
    }


def test_pass_geometry_metrics_cover_only_passes_with_coordinates():
    from inside_game.insights.adapters import pass_geometry_metrics

    events = [
        pass_event(40, 34, 70, 40),  # completo y progresivo (+21 m hacia portería)
        pass_event(65, 34, 100, 34),  # completo, progresivo y entra al último tercio
        pass_event(50, 34, None, None, "Incomplete"),  # sin destino: no cuenta
        {"attacking_x_m": 10, "attacking_y_m": 10},  # no es un pase
    ]
    found = pass_geometry_metrics(events)
    assert found["progressive_passes_with_geometry"] == 2
    assert found["final_third_entries_with_geometry"] == 1
    assert found["total_pass_length_with_geometry_m"] > 0
    assert pass_geometry_metrics([events[2], events[3]]) == {}


def test_pass_map_fills_missing_api_totals_from_events_and_labels_the_subset():
    from inside_game.insights.demo import demo_manifest
    from inside_game.insights.pages import compile_report

    manifest = demo_manifest()
    block = next(b for b in manifest["blocks"] if b["insight_id"] == "pass_map")
    block = copy.deepcopy(block)
    for field in ("team_id", "period", "time_ms"):  # la evidencia es de todo el partido
        block["parameters"].pop(field)
    evidence = copy.deepcopy(
        [
            e
            for e in manifest["evidence"]
            if e["evidence_id"] in set(block["evidence_ids"])
        ]
    )
    summary = next(e for e in evidence if e["operation"] == "get_passes")["response"][
        "data"
    ]["summary"]
    for key in ("progressive_passes", "final_third_entries", "total_pass_length_m"):
        summary[key] = None
    for item in next(e for e in evidence if e["operation"] == "get_passes")["response"][
        "data"
    ]["items"]:
        item["attacking_x_m"], item["attacking_y_m"] = 40, 34
        item["pass"].update(end_x=100, end_y=40, outcome=None)
    _, [compiled] = compile_report(
        {"title": "Pases", "blocks": [block], "evidence": evidence}
    )
    keys = {k.split(".")[-1] for k in compiled.metrics}
    assert "progressive_passes_with_geometry" in keys
    assert not keys & {"progressive_passes", "final_third_entries"}
    assert "sólo con coordenadas" in metric_label("progressive_passes_with_geometry")
