"""La evaluación no debe reactivar un modelo que el titular descartó."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace


def test_verification_does_not_reactivate_unselected_model(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import verify_data_agent

    monkeypatch.setattr(verify_data_agent, "ROOT", tmp_path)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    (tmp_path / "deployment").mkdir()
    (tmp_path / "deployment/cloud.json").write_text(
        json.dumps({"url": "https://example.azurecontainerapps.io"}), encoding="utf-8"
    )
    (tmp_path / "deployment/agent-model.json").write_text(
        json.dumps(
            {
                "model": "gpt-oss-120b",
                "deployment_created": True,
                "selected_for_agent": False,
            }
        ),
        encoding="utf-8",
    )
    credential = tmp_path / "agent-data.json"
    credential.write_text(
        json.dumps({"credential_id": "agent-data", "key": "test-secret-not-real"}),
        encoding="utf-8",
    )

    def forbidden_model(*args, **kwargs):
        raise AssertionError("Unselected model must never be instantiated")

    monkeypatch.setattr(verify_data_agent, "create_model", forbidden_model)
    report_path = tmp_path / "report.json"
    assert not asyncio.run(
        verify_data_agent.verify(
            SimpleNamespace(private_file=credential, report=report_path, case=None)
        )
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "blocked"
    assert report["reason"] == "MODEL_NOT_SELECTED"
    assert report["llm_used"] is False
    assert "test-secret-not-real" not in report_path.read_text(encoding="utf-8")


def test_evidence_comparison_ignores_only_opaque_cursor_refresh(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    from verify_data_agent import comparable_response

    original = {
        "data": {"items": [{"x": 1.25}]},
        "pagination": {"next_cursor": "old"},
        "warnings": ["missing xG"],
    }
    refreshed = {**original, "pagination": {"next_cursor": "new"}}
    assert comparable_response(original) == comparable_response(refreshed)
    assert comparable_response(original) != comparable_response(
        {**refreshed, "pagination": {"next_cursor": None}}
    )
    assert comparable_response(original) != comparable_response(
        {**refreshed, "data": {"items": [{"x": 1.26}]}}
    )
    assert comparable_response(original) != comparable_response(
        {**refreshed, "warnings": []}
    )
