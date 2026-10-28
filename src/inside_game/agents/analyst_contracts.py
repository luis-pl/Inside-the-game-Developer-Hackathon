"""Contrato del intérprete al analista; texto deportivo con referencias auditables."""

from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field

from inside_game.agents.contracts import (
    DataContext,
    DataRequest,
    DataResult,
    Evidence,
    Message,
)
from inside_game.agents.insight_contracts import InsightResult
from inside_game.insights.catalog import InsightId
from inside_game.insights.contracts import AnalystNote
from inside_game.language import Language


class AnalysisRequest(DataRequest):
    data_result: DataResult | None = None
    review_visuals: bool = True
    required_insights: list[InsightId] = Field(default_factory=list, max_length=40)


class Fact(Message):
    id: str
    value: float | int | str
    label: str
    evidence_ids: list[str]
    operation: str
    path: str
    scope: dict
    provenance: dict
    block_id: str | None = None
    unit: str | None = None


class Statement(Message):
    kind: Literal["observation", "interpretation", "recommendation"]
    text: str = Field(min_length=1, max_length=1200)
    fact_ids: list[str] = Field(min_length=1, max_length=100)


class AnalysisSection(Message):
    heading: str = Field(min_length=1, max_length=120)
    statements: list[Statement] = Field(min_length=1, max_length=8)


class FinishAnalysis(Message):
    status: Literal["complete", "partial", "needs_clarification", "unsupported"]
    title: str = Field(default="Análisis deportivo", max_length=160)
    sections: list[AnalysisSection] = Field(default_factory=list, max_length=8)
    limitations: list[str] = Field(default_factory=list, max_length=12)
    clarification: str | None = Field(default=None, max_length=1200)


class EarlyAnalysis(Message):
    status: Literal["needs_clarification", "unsupported"]
    clarification: str = Field(min_length=1, max_length=1200)


class VisualRequest(Message):
    request_text: str = Field(min_length=1, max_length=4000)


class AttachAnalysis(Message):
    request_id: UUID = Field(default_factory=uuid4)
    expected_revision: int = Field(strict=True, ge=1)
    analyst: AnalystNote


class AnalysisResult(Message):
    request_id: UUID
    language: Language = "es"
    status: Literal[
        "complete", "partial", "needs_clarification", "unsupported", "error"
    ]
    text: str = ""
    sections: list[AnalysisSection] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    clarification: str | None = None
    issues: list[str] = Field(default_factory=list)
    model: str
    prompt_sha256: str = ""
    elapsed_ms: float = 0
    model_turns: int = 0
    total_tokens: int = 0
    context_events: list[dict] = Field(default_factory=list)
    tool_trace: list[dict] = Field(default_factory=list)
    data_request_ids: list[UUID] = Field(default_factory=list)
    visual_report: InsightResult | None = None
    # Sólo el anfitrión conserva originales para el siguiente agente.
    evidence: list[Evidence] = Field(default_factory=list, exclude=True)
    context: DataContext = Field(default_factory=DataContext, exclude=True)
    visual_evidence_aliases: dict[str, str] = Field(default_factory=dict, exclude=True)


class AnalysisReportResult(Message):
    request_id: UUID
    analysis: AnalysisResult
    report: InsightResult | None = None
