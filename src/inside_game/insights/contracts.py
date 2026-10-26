"""Contratos de composición; ninguna entrada acepta código, URLs o credenciales."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from inside_game.agents.contracts import Evidence
from inside_game.insights.catalog import RECIPES
from inside_game.service import OPERATIONS


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Parameters(Closed):
    team_id: Annotated[int | None, Field(strict=True, gt=0)] = None
    player_id: Annotated[int | None, Field(strict=True, gt=0)] = None
    period: Literal[1, 2] | None = None
    time_ms: Annotated[int | None, Field(strict=True, ge=0)] = None
    # Roles explícitos aportados por el anfitrión; nunca inferidos por camiseta.
    defender_ids: list[Annotated[int, Field(strict=True, gt=0)]] = Field(
        default_factory=list, max_length=11
    )
    midfielder_ids: list[Annotated[int, Field(strict=True, gt=0)]] = Field(
        default_factory=list, max_length=11
    )
    goalkeeper_id: Annotated[int | None, Field(strict=True, gt=0)] = None
    attack_positive_x: bool | None = None
    epsilon_m: Literal[5, 10, 15, 20] = 15
    mode: Literal["clique", "graph"] = "clique"
    max_gap_ms: Annotated[int, Field(strict=True, ge=200, le=5000)] = 1000
    tolerance_ms: Annotated[int, Field(strict=True, ge=0, le=1000)] = 200
    pressure_window_s: Annotated[float, Field(gt=0, le=15)] = 5

    @model_validator(mode="after")
    def distinct_roles(self):
        defenders, midfielders = set(self.defender_ids), set(self.midfielder_ids)
        if defenders & midfielders or self.goalkeeper_id in defenders | midfielders:
            raise ValueError("ROLE_GROUPS_OVERLAP")
        if len(defenders) != len(self.defender_ids) or len(midfielders) != len(
            self.midfielder_ids
        ):
            raise ValueError("DUPLICATE_ROLE_ID")
        if self.time_ms is not None and self.period is None:
            raise ValueError("TIME_REQUIRES_PERIOD")
        return self


class TeamStyle(Closed):
    """Identidad de presentación; no modifica los datos del proveedor."""

    team_id: Annotated[int, Field(strict=True, gt=0)]
    name: str | None = Field(default=None, max_length=100)
    color: Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]


class VisualOptions(Closed):
    span: Literal["auto", "full", "half"] = "auto"
    show_labels: bool = True
    show_legend: bool = True
    min_edge_weight: Annotated[int, Field(strict=True, ge=1, le=100)] = 1


class BlockSpec(Closed):
    id: Annotated[str, Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,59}$")]
    insight_id: str = Field(json_schema_extra={"enum": list(RECIPES)})
    evidence_ids: list[str] = Field(min_length=1, max_length=100)
    title: str | None = Field(default=None, max_length=180)
    parameters: Parameters = Field(default_factory=Parameters)
    visual: VisualOptions = Field(default_factory=VisualOptions)

    @model_validator(mode="after")
    def known_recipe(self):
        if self.insight_id not in RECIPES:
            raise ValueError("UNKNOWN_INSIGHT")
        return self


class AnalystNote(Closed):
    """Texto aportado por el analista; el compositor no inventa su contenido."""

    text: str = Field(min_length=1, max_length=16000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)


class ReportPlan(Closed):
    title: str = Field(default="Informe de fútbol", min_length=1, max_length=180)
    template_id: Literal[
        "match_overview",
        "player_dossier",
        "entity_comparison",
        "tactical_episode",
        "custom_report",
    ] = "custom_report"
    blocks: list[BlockSpec] = Field(min_length=1, max_length=40)
    teams: list[TeamStyle] = Field(default_factory=list, max_length=20)
    analyst: AnalystNote | None = None

    @model_validator(mode="after")
    def unique_team_styles(self):
        if len({t.team_id for t in self.teams}) != len(self.teams):
            raise ValueError("DUPLICATE_TEAM_STYLE")
        return self


class ReportSpec(ReportPlan):
    evidence: list[Evidence] = Field(min_length=1, max_length=100)
    # Recetas que la fuente no anota (perfil medido): sus contadores en cero no
    # acreditan ausencia y el bloque se marca `empty_with_coverage`.
    zero_only_insights: list[str] = Field(default_factory=list, max_length=40)
    # Métricas que la fuente no anota (receta → claves): en cero no son un cero real.
    unannotated_metrics: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_references(self):
        ids = [e.evidence_id for e in self.evidence]
        if len(set(ids)) != len(ids) or len({b.id for b in self.blocks}) != len(
            self.blocks
        ):
            raise ValueError("DUPLICATE_ID")
        if any(set(b.evidence_ids) - set(ids) for b in self.blocks):
            raise ValueError("UNKNOWN_EVIDENCE")
        if self.analyst and set(self.analyst.evidence_ids) - set(ids):
            raise ValueError("UNKNOWN_ANALYST_EVIDENCE")
        if any(
            e.operation not in OPERATIONS or e.operation != e.response.operation_id
            for e in self.evidence
        ):
            raise ValueError("INVALID_EVIDENCE_OPERATION")
        if len(self.model_dump_json().encode()) > 8 * 1024 * 1024:
            raise ValueError("EVIDENCE_BUDGET_EXCEEDED")
        return self


class BlockData(Closed):
    id: str
    insight_id: str
    title: str
    state: Literal[
        "ready",
        "empty_with_coverage",
        "partial",
        "unavailable",
        "incompatible",
        "error",
    ] = "ready"
    method_id: str
    evidence_ids: list[str]
    warnings: list[str] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
    points: list[dict] = Field(default_factory=list)
    vectors: list[dict] = Field(default_factory=list)
    series: list[dict] = Field(default_factory=list)
    rows: list[dict] = Field(default_factory=list)
    polygons: list[dict] = Field(default_factory=list)
    frames: list[dict] = Field(default_factory=list)
    markers: list[dict] = Field(default_factory=list)
    # Métricas por equipo (id de equipo → clave → valor) de las piezas de partido.
    by_team: dict = Field(default_factory=dict)
    scope: list[dict] = Field(default_factory=list)
    unit: str | None = None
    teams: dict = Field(default_factory=dict)
    players: dict = Field(default_factory=dict)
    visual: VisualOptions = Field(default_factory=VisualOptions)
    layout: Literal["pitch", "schematic"] = "pitch"
    coordinate_reference: Literal["fixed_tracking", "acting_team_attack"] = (
        "fixed_tracking"
    )
