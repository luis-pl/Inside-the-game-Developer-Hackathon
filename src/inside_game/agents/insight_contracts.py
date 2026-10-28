"""Mensajes v1 entre intérprete/analista, insights y data; sin destinos ni claves."""

from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from inside_game.agents.contracts import DataContext, DataResult, Evidence, Message
from inside_game.insights.catalog import InsightId
from inside_game.insights.contracts import AnalystNote, BlockSpec, ReportPlan, TeamStyle
from inside_game.language import Language


class InsightRequest(Message):
    request_id: UUID = Field(default_factory=uuid4)
    language: Language = "es"
    original_request: str | None = Field(default=None, max_length=4000)
    required_insights: list[InsightId] = Field(default_factory=list, max_length=40)
    request_text: str = Field(min_length=1, max_length=8000)
    context: DataContext = Field(default_factory=DataContext)
    data_result: DataResult | None = None
    analyst: AnalystNote | None = None
    report_id: UUID | None = None
    expected_revision: int | None = Field(default=None, strict=True, ge=1)

    @field_validator("request_text")
    @classmethod
    def meaningful(cls, value):
        if not value.strip():
            raise ValueError("EMPTY_INTENT")
        return value

    @model_validator(mode="after")
    def revision_required(self):
        if (self.report_id is None) != (self.expected_revision is None):
            raise ValueError("REPORT_AND_REVISION_REQUIRED_TOGETHER")
        return self


class RetrieveData(Message):
    request_text: str = Field(min_length=1, max_length=8000)
    context: DataContext = Field(default_factory=DataContext)


class FinishInsight(Message):
    status: Literal["needs_clarification", "unsupported"]
    clarification: str = Field(min_length=1, max_length=1500)


class ReportChanges(Message):
    """Patch declarativo: añadir conserva automáticamente los demás bloques."""

    title: str | None = Field(default=None, min_length=1, max_length=180)
    add_blocks: list[BlockSpec] = Field(default_factory=list, max_length=40)
    replace_blocks: list[BlockSpec] = Field(default_factory=list, max_length=40)
    remove_block_ids: list[str] = Field(default_factory=list, max_length=40)
    order_ids: list[str] | None = Field(default=None, max_length=40)
    teams: list[TeamStyle] = Field(default_factory=list, max_length=20)

    def apply(self, previous):
        plan = previous.model_dump(mode="json")
        existing = {b.id: b for b in previous.blocks}
        removed, replaced, added = (
            set(self.remove_block_ids),
            {b.id for b in self.replace_blocks},
            {b.id for b in self.add_blocks},
        )
        if (
            not (removed | replaced) <= existing.keys()
            or removed & replaced
            or added & existing.keys()
        ):
            raise ValueError("INVALID_BLOCK_PATCH")
        if len(replaced) != len(self.replace_blocks) or len(added) != len(
            self.add_blocks
        ):
            raise ValueError("DUPLICATE_BLOCK_PATCH")
        blocks = {key: value for key, value in existing.items() if key not in removed}
        blocks.update({b.id: b for b in self.replace_blocks + self.add_blocks})
        order = self.order_ids if self.order_ids is not None else list(blocks)
        if len(order) != len(set(order)) or set(order) != set(blocks):
            raise ValueError("INVALID_BLOCK_ORDER")
        plan["blocks"] = [blocks[key].model_dump(mode="json") for key in order]
        if self.title is not None:
            plan["title"] = self.title
        teams = {t.team_id: t for t in previous.teams}
        teams.update({t.team_id: t for t in self.teams})
        plan["teams"] = [t.model_dump() for t in teams.values()]
        return ReportPlan.model_validate(plan)


class InsightResult(Message):
    request_id: UUID
    status: Literal[
        "complete", "partial", "needs_clarification", "unsupported", "error"
    ]
    report_id: UUID | None = None
    revision: int | None = None
    artifact_url: str | None = None
    clarification: str | None = None
    issues: list[str] = Field(default_factory=list)
    blocks: list[dict] = Field(default_factory=list)
    model: str
    model_turns: int = 0
    tool_calls: int = 0
    tool_trace: list[dict] = Field(default_factory=list)
    total_tokens: int = 0
    context_events: list[dict] = Field(default_factory=list)
    elapsed_ms: float = 0
    timings_ms: dict[str, float] = Field(default_factory=dict)
    data_request_ids: list[UUID] = Field(default_factory=list)
    data_runs: list[dict] = Field(default_factory=list)
    prompt_sha256: str = ""
    # Sólo el anfitrión conserva HTML, plan y originales; no van al LLM/JSON HTTP.
    html: str | None = Field(default=None, exclude=True)
    plan: ReportPlan | None = Field(default=None, exclude=True)
    evidence: list[Evidence] = Field(default_factory=list, exclude=True)
