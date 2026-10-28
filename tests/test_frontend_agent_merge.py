"""Cross-branch regressions: language, provenance and safe failure diagnostics."""

import asyncio
from types import SimpleNamespace
from typing import get_args

import pytest

from inside_game.agents.analyst_contracts import AnalysisRequest
from inside_game.agents.sports_analyst import SportsAnalyst, _Run
from inside_game.insights.analysis_note import analyst_copy
from inside_game.insights.demo import demo_manifest
from inside_game.insights.pages import render_report
from inside_game.language import Language, wording


@pytest.mark.parametrize("language", get_args(Language))
def test_unknown_provenance_remains_unknown_in_every_report_language(language):
    manifest = demo_manifest()
    manifest["blocks"] = [
        b for b in manifest["blocks"] if b["insight_id"] == "shot_map"
    ]
    manifest["language"] = language
    for ev in manifest["evidence"]:
        ev["response"]["provenance"].pop("is_synthetic", None)
    html = render_report(manifest)["html"]
    assert wording("unknown_provenance", language) in html
    assert f'<html lang="{language}">' in html


@pytest.mark.parametrize("source_language", get_args(Language))
def test_legacy_note_can_be_presented_with_another_interface_language(source_language):
    note = (
        "Analysis\nA finding.\n"
        + wording("limits", source_language)
        + "\nMain limitation.\nMore scope.\n"
        + wording("references", source_language)
        + "\n[1] <source>"
    )
    html = analyst_copy(note, language="en")
    assert "Main limitation." in html.split("<details")[0]
    assert "<summary>Sources and references</summary>" in html
    assert "[1] &lt;source&gt;" in html


@pytest.mark.parametrize(
    "code",
    [
        "FACT_BUDGET_EXCEEDED",
        "EVIDENCE_BUDGET_EXCEEDED",
        "EVIDENCE_MATCH_MISMATCH",
        "private transport error with secret",
    ],
)
def test_selected_experimental_diagnostics_expose_only_public_codes(monkeypatch, code):
    async def fails(self):
        raise ValueError(code)

    monkeypatch.setattr(_Run, "execute", fails)
    result = asyncio.run(
        SportsAnalyst(SimpleNamespace(name="offline")).run(
            AnalysisRequest(request_text="Review")
        )
    )
    expected = "INVALID_ANALYSIS_DATA" if code.startswith("private") else code
    assert result.status == "error" and result.issues == [expected]
    assert "secret" not in result.model_dump_json()
