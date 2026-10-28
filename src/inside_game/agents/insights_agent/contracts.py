"""Intención del usuario y plan resuelto. El LLM sólo puede producir la intención."""

from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from inside_game.agents.contracts import Message
from inside_game.contracts import Id
from inside_game.insights.catalog import RECIPES
from inside_game.language import Language

TemplateId = Literal[
    "match_overview",
    "player_dossier",
    "entity_comparison",
    "tactical_episode",
    "custom_report",
]


class InsightIntent(Message):
    """Qué quiere ver el usuario; sin operaciones, argumentos ni cifras."""

    language: Language = "es"
    template_id: TemplateId
    match_id: Id
    # Equipo protagonista; por defecto, el local.
    team_id: Id | None = None
    player_id: Id | None = None
    compare_kind: Literal["team", "player"] = "team"
    # Vacío en una comparación de equipos: local y visitante.
    compare_ids: Annotated[list[Id], Field(max_length=2)] = Field(default_factory=list)
    period: Literal[1, 2] | None = None
    time_ms: Annotated[int | None, Field(strict=True, ge=0)] = None
    insight_ids: Annotated[list[str], Field(max_length=30)] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def coherent(self):
        if unknown := set(self.insight_ids) - set(RECIPES):
            raise ValueError(f"UNKNOWN_INSIGHT: {sorted(unknown)}")
        if self.template_id == "custom_report" and not self.insight_ids:
            raise ValueError("custom_report requires insight_ids")
        if self.template_id == "player_dossier" and self.player_id is None:
            raise ValueError("player_dossier requires player_id")
        if self.compare_kind == "player" and len(set(self.compare_ids)) != 2:
            raise ValueError("player comparison requires two distinct compare_ids")
        if (
            self.compare_kind == "team"
            and self.compare_ids
            and len(set(self.compare_ids)) != 2
        ):
            raise ValueError("team comparison requires two distinct compare_ids")
        if self.time_ms is not None and self.period is None:
            raise ValueError("time_ms requires period")
        return self


class QuerySpec(Message):
    key: str
    operation: str
    arguments: dict


class BlockPlan(Message):
    id: str
    insight_id: str
    title: str
    query_keys: list[str]
    parameters: dict


class Discarded(Message):
    insight_id: str
    team_id: int | None = None
    reason: str


class PlanLabels(Message):
    """Nombres para presentar el plan; vienen del contexto del partido."""

    match: str
    competition: str | None = None
    home_team: str
    away_team: str
    focus_team: str
    player: str | None = None
    provider: str | None = None
    data_kind: str | None = None
    synthetic: bool


class ResolvedPlan(Message):
    intent: InsightIntent
    source: str
    labels: PlanLabels
    home_team_id: int
    away_team_id: int
    focus_team_id: int
    # Con perfil medido, las acciones que la fuente no anota ya se descartaron.
    profile_measured: bool = False
    # Recetas que la fuente no anota: el compilador no las acepta con sólo ceros.
    zero_only_insights: list[str] = Field(default_factory=list)
    unannotated_metrics: dict[str, list[str]] = Field(default_factory=dict)
    queries: list[QuerySpec]
    blocks: list[BlockPlan]
    discarded: list[Discarded] = Field(default_factory=list)
    # Decisiones del anfitrión que el usuario no dijo: se muestran, no se ocultan.
    decisions: dict = Field(default_factory=dict)


class Clarification(Message):
    question: Annotated[str, Field(min_length=1, max_length=500)]
    options: Annotated[
        list[Annotated[str, Field(max_length=200)]], Field(max_length=6)
    ] = Field(default_factory=list)


class Previous(Message):
    """Estado de la conversación que el cliente devuelve tal cual (`answer.next`).

    El agente no guarda sesiones: la intención anterior permite seguimientos y la
    aclaración pendiente, junto con la pregunta que la originó, permite que una
    respuesta como "el segundo" se entienda.
    """

    intent: InsightIntent | None = None
    clarification: Clarification | None = None
    question: Annotated[str | None, Field(max_length=2000)] = None


class AskRequest(Message):
    request_id: UUID = Field(default_factory=uuid4)
    language: Language = "es"
    question: Annotated[str | None, Field(min_length=1, max_length=2000)] = None
    intent: InsightIntent | None = None
    previous: Previous | None = None

    @model_validator(mode="after")
    def one_input(self):
        if (self.question is None) == (self.intent is None):
            raise ValueError("Send exactly one of question or intent")
        if self.question is not None and not self.question.strip():
            raise ValueError("question must contain text")
        return self


class BlockSummary(Message):
    id: str
    insight_id: str
    title: str
    state: str
    warnings: list[str]
    # Claves estables, sin ID de consulta: aptas para el analista o un narrador.
    metrics: dict


class InsightAnswer(Message):
    """Respuesta pequeña; el informe HTML viaja aparte."""

    request_id: UUID
    kind: Literal["report", "clarification", "declined", "error"]
    summary: str
    # Para interfaces: el título del informe y las decisiones del agente por separado.
    title: str | None = None
    notes: list[str] = Field(default_factory=list)
    intent: InsightIntent | None = None
    clarification: Clarification | None = None
    labels: PlanLabels | None = None
    blocks: list[BlockSummary] = Field(default_factory=list)
    discarded: list[Discarded] = Field(default_factory=list)
    decisions: dict = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)
    has_report: bool = False
    next: Previous | None = None
    timings_ms: dict = Field(default_factory=dict)
