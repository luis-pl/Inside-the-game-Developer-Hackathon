"""Cada pieza responde su pregunta con una cifra, para las 30 recetas.

Usa la galería sintética (una pieza por receta) para que añadir o cambiar una
receta no pueda volver a mostrar datos sin lectura ni dejar claves de la API en
la frase.
"""

import re

import pytest

from inside_game.insights.catalog import RECIPES
from inside_game.insights.contracts import BlockData
from inside_game.insights.demo import demo_manifest
from inside_game.insights.headlines import HEADLINES, headline, plural
from inside_game.insights.pages import compile_report, render_report

MANIFEST = demo_manifest()
REQUEST = {
    "title": "Galería",
    "blocks": MANIFEST["blocks"],
    "evidence": MANIFEST["evidence"],
}
_, BLOCKS = compile_report(REQUEST)
BY_RECIPE = {b.insight_id: b for b in BLOCKS}
HTML = render_report(REQUEST)["html"]
RAW = re.compile(
    r"[a-z]+_[a-z_]+|\b[a-z]+\.[a-z_]+\b|\b(None|NaN|nan|undefined|null)\b"
)
TEAMS = {
    "1": {"name": "Home", "color": "#2463bc"},
    "2": {"name": "Visita", "color": "#bf402e"},
}


def block(insight_id, **fields):
    base = {
        "id": insight_id,
        "insight_id": insight_id,
        "title": insight_id,
        "method_id": "m",
        "evidence_ids": ["e1"],
    }
    return BlockData(**{**base, **fields})


def test_there_is_a_headline_for_every_recipe_in_the_catalog():
    assert set(HEADLINES) == set(RECIPES)
    assert len(BY_RECIPE) == len(RECIPES) == 30


@pytest.mark.parametrize("recipe", sorted(BY_RECIPE))
def test_every_recipe_answers_with_a_clean_english_sentence(recipe):
    line = headline(BY_RECIPE[recipe])
    assert line, f"{recipe} no tiene lectura"
    assert line[0].isupper() or line[0].isdigit()
    assert line.endswith(".")
    assert not RAW.search(line), line
    assert "1 passes" not in line and "1 actions" not in line, line


def test_every_rendered_piece_shows_its_answer_right_under_the_question():
    sections = re.findall(
        r'<section class="insight".*?</section>', HTML, flags=re.DOTALL
    )
    assert len(sections) == 30
    for section in sections:
        assert re.search(
            r'class="block-question">[^<]*</p><p class="block-answer">', section
        ), section[:200]


def test_blocks_that_are_not_shown_have_no_answer_line():
    assert headline(block("shot_map", state="unavailable")) is None
    assert headline(block("shot_map", state="error")) is None


def test_recovery_time_answers_with_median_mean_and_maximum():
    rows = [{"recovery_s": v} for v in (10, 30, 20, 100)]
    assert headline(block("ball_recovery_time", rows=rows)) == (
        "Median of 25 s to recover the ball after losing it "
        "(mean 40 s, maximum 100 s; 4 recoveries)."
    )
    one = headline(block("ball_recovery_time", rows=[{"recovery_s": 8}]))
    assert "1 recovery)" in one


def test_shot_headline_splits_by_team_and_counts_goals():
    points = (
        [{"team_id": 1, "outcome": "Goal"}] * 2
        + [{"team_id": 1, "outcome": "Saved"}]
        + [{"team_id": 2, "outcome": "Off T"}]
    )
    line = headline(block("shot_map", points=points, teams=TEAMS))
    assert line == "Home: 3 shots (2 goals); Visita: 1 shot."


def test_lane_headline_names_the_busiest_lane_and_its_share():
    values = (7, 4, 2, 2, 0)
    metrics = {f"q1.channel_{n}": v for n, v in zip(range(1, 6), values, strict=True)}
    line = headline(block("final_third_channels", metrics=metrics))
    assert line == "15 entries into the final third; channel 1 accounted for 7 (47%)."
    empty = {f"q1.channel_{n}": 0 for n in range(1, 6)}
    assert "No final-third entries" in headline(
        block("final_third_channels", metrics=empty)
    )


def test_comparison_headline_pits_the_two_entities_against_each_other():
    rows = [
        {"entity_id": 1, "metrics": {"aggregate": {"shots": 5, "goals": 2}}},
        {"entity_id": 2, "metrics": {"aggregate": {"shots": 3, "goals": 0}}},
    ]
    line = headline(block("entity_comparison", rows=rows, teams=TEAMS))
    assert line == "Shots: Home 5 versus Visita 3; Goals: Home 2 versus Visita 0."


def test_comparison_ignores_source_categories_as_headline_figures():
    rows = [
        {"entity_id": 1, "metrics": {"body_parts": {"Head": 1}, "shots": 5}},
        {"entity_id": 2, "metrics": {"body_parts": {"Head": 2}, "shots": 3}},
    ]
    line = headline(block("entity_comparison", rows=rows, teams=TEAMS))
    assert "Head" not in line and "Shots" in line


def test_line_breaks_headline_agrees_in_number():
    one = headline(block("defensive_geometry", metrics={"q1.observed_line_breaks": 1}))
    many = headline(
        block("defensive_geometry", metrics={"q1.observed_line_breaks": 47})
    )
    assert one == "1 pass crossed opposition defensive lines."
    assert many == "47 passes crossed opposition defensive lines."


def test_a_headline_never_raises_on_odd_data():
    assert headline(block("hodge_flow", metrics={"q1.gradient_fraction": None})) is None
    assert headline(block("movement_profile", rows=[{"distance_m": "x"}])) is None
    assert headline(block("match_timeline")) is None
    assert headline(block("ball_recovery_time", rows=[{"recovery_s": "x"}])) is None


def test_plural_agrees_in_number():
    assert plural(1, "pieza", "piezas") == "1 pieza"
    assert plural(0, "pieza", "piezas") == "0 piezas"
    assert plural(2, "pieza", "piezas") == "2 piezas"


def test_pressure_headline_describes_the_events_really_shown():
    rows = (
        [{"type_name": "Interception"}] * 5
        + [{"type_name": "Ball Recovery"}] * 3
        + [{"type_name": "Goal Keeper"}]
    )
    line = headline(block("pressure_recovery", rows=rows))
    assert line == (
        "9 recorded actions (Interceptions 5, Recoveries 3, "
        "Goalkeeper actions 1); the source does not annotate pressures in this scope."
    )
    with_pressure = headline(
        block("pressure_recovery", rows=[{"type_name": "Pressure"}] * 2)
    )
    assert "does not annotate pressures" not in with_pressure


def test_between_lines_headline_counts_each_reception_category():
    rows = [
        {"category": "between_lines"},
        {"category": "between_lines"},
        {"category": "behind_defense"},
        {"category": "in_front"},
    ]
    metrics = {"q1.computed_passes": 4, "q1.eligible_passes": 6}
    line = headline(block("between_lines_receptions", rows=rows, metrics=metrics))
    assert line == (
        "Between-lines receptions: 2 out of 4 evaluated passes (from 6 eligible passes) "
        "(1 behind the defence, 1 in front of the opposition midfield)."
    )


def test_rows_that_are_not_what_a_recipe_expects_do_not_break_the_report():
    odd = block("passing_network", rows=[{"passes": 3}])  # falta source/target
    assert headline(odd) is None
