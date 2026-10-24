"""Closed, typed request contracts shared by HTTP and the MCP adapter."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Id = Annotated[int, Field(strict=True, gt=0)]
Profile = Literal[
    "finishing",
    "chance_creation",
    "passing",
    "defending",
    "ball_progression",
    "movement",
    "set_pieces",
    "possession_sequences",
    "goalkeeping",
    "pressure_effectiveness",
    "ppda_demo",
]
Zone = Literal[
    "all",
    "defensive_third",
    "middle_third",
    "final_third",
    "penalty_area",
    "central_channel",
]


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)

    @model_validator(mode="before")
    @classmethod
    def no_boolean_numbers(cls, value):
        if isinstance(value, dict) and any(type(v) is bool for v in value.values()):
            raise ValueError("Boolean values are not accepted by this contract")
        return value


class MatchScope(ClosedModel):
    kind: Literal["match"] = "match"


class PeriodScope(ClosedModel):
    kind: Literal["period"]
    period: Literal[1, 2]


class WindowScope(ClosedModel):
    kind: Literal["window"]
    period: Literal[1, 2]
    start_ms: Annotated[int, Field(strict=True, ge=0)]
    end_ms: Annotated[int, Field(strict=True, gt=0)]

    @model_validator(mode="after")
    def ordered(self):
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self


Scope = Annotated[MatchScope | PeriodScope | WindowScope, Field(discriminator="kind")]


class Empty(ClosedModel):
    pass


class Page(ClosedModel):
    limit: Annotated[int, Field(strict=True, ge=1, le=200)] = 100
    cursor: Annotated[str | None, Field(max_length=1024)] = None


class EntitySearch(Page):
    kind: Literal["team", "player"]
    name: Annotated[str, Field(min_length=1, max_length=80)]
    match_id: Id | None = None


class MatchList(Page):
    team_id: Id | None = None
    opponent_id: Id | None = None
    from_date: date | None = None
    to_date: date | None = None
    side: Literal["all", "home", "away"] = "all"


class MatchRequest(ClosedModel):
    match_id: Id


class Filtered(MatchRequest, Page):
    team_id: Id | None = None
    player_id: Id | None = None
    scope: Scope = Field(default_factory=MatchScope)
    zone_id: Zone = "all"
    score_state: Literal["all", "leading", "tied", "trailing"] = "all"
    pressure: Literal["all", "under_pressure", "unpressured"] = "all"
    view: Literal["events", "summary", "map", "timeline"] = "events"
    bin_s: Literal[60, 300, 900] = 300


class ShotsRequest(Filtered):
    outcome: Literal["all", "on_target", "goal", "saved", "blocked", "off_target"] = (
        "all"
    )
    body_part: Literal["all", "head", "left_foot", "right_foot"] = "all"


class PassesRequest(Filtered):
    outcome: Literal["all", "complete", "incomplete"] = "all"
    height: Literal["all", "ground", "low", "high"] = "all"
    restart: Literal[
        "all", "regular", "corner", "throw_in", "free_kick", "goal_kick", "kick_off"
    ] = "all"
    tagged: Literal[
        "all", "cross", "cut_back", "switch", "shot_assist", "goal_assist"
    ] = "all"


class DefensiveRequest(Filtered):
    kind: Literal[
        "all",
        "pressure",
        "tackle",
        "interception",
        "aerial_duel",
        "clearance",
        "block",
        "recovery",
        "fifty_fifty",
        "goalkeeper",
    ] = "all"
    outcome: Literal["all", "won", "lost"] = "all"


class BallRequest(Filtered):
    kind: Literal[
        "all", "dribble", "carry", "receipt", "miscontrol", "dispossessed"
    ] = "all"
    outcome: Literal["all", "complete", "incomplete"] = "all"


class EventsRequest(Filtered):
    event_types: Annotated[
        list[
            Literal[
                2,
                3,
                4,
                6,
                9,
                10,
                14,
                16,
                17,
                18,
                19,
                21,
                22,
                23,
                30,
                33,
                34,
                35,
                36,
                38,
                39,
                42,
                43,
            ]
        ],
        Field(max_length=23),
    ] = Field(default_factory=list)


class SummaryRequest(ClosedModel):
    match_ids: Annotated[list[Id], Field(min_length=1, max_length=10)]
    scope: Scope = Field(default_factory=MatchScope)
    profile_id: Profile = "finishing"
    zone_id: Zone = "all"
    score_state: Literal["all", "leading", "tied", "trailing"] = "all"
    pressure: Literal["all", "under_pressure", "unpressured"] = "all"


class TeamSummary(SummaryRequest):
    team_id: Id


class PlayerSummary(SummaryRequest):
    player_id: Id


class TrackingFrame(MatchRequest):
    run_id: UUID | None = None
    period: Literal[1, 2]
    time_ms: Annotated[int, Field(strict=True, ge=0)]


class TrackingWindow(MatchRequest):
    run_id: UUID | None = None
    scope: WindowScope
    stride_s: Literal[1, 2, 5] = 1
    sample_step_ms: Literal[200, 1000] | None = None
    team_id: Id | None = None
    player_id: Id | None = None

    @model_validator(mode="after")
    def sampling_not_ambiguous(self):
        if self.sample_step_ms is not None and self.stride_s != 1:
            raise ValueError("Use sample_step_ms or stride_s, not both")
        return self


class EventContext(ClosedModel):
    event_id: UUID
    before_s: Literal[0, 5, 10, 15] = 5
    after_s: Literal[0, 5, 10, 15] = 5


class HeatmapRequest(Filtered):
    mode: Literal["event_count", "occupancy_seconds"] = "occupancy_seconds"
    grid_id: Literal["5m", "10m"] = "5m"
    event_type: Literal[
        "all", "shot", "pass", "pressure", "dribble", "carry", "interception"
    ] = "all"


class MovementRequest(MatchRequest):
    scope: Scope = Field(default_factory=MatchScope)
    team_id: Id | None = None
    player_id: Id | None = None


class MetricSeries(Filtered):
    profile_id: Profile = "finishing"


class CompareRequest(SummaryRequest):
    mode: Literal["entities", "windows"] = "entities"
    entity_kind: Literal["team", "player"]
    entity_ids: Annotated[list[Id], Field(min_length=1, max_length=2)]
    windows: Annotated[list[Scope], Field(max_length=2)] = Field(default_factory=list)

    @model_validator(mode="after")
    def comparison(self):
        if self.mode == "entities" and (len(set(self.entity_ids)) != 2 or self.windows):
            raise ValueError(
                "entities mode requires two distinct entities and no windows"
            )
        if self.mode == "windows" and (
            len(self.entity_ids) != 1
            or len(self.windows) != 2
            or len(self.match_ids) != 1
        ):
            raise ValueError(
                "windows mode requires one entity, one match and two scopes"
            )
        return self


class SetPiecesRequest(Filtered):
    restart: Literal[
        "all", "corner", "throw_in", "free_kick", "goal_kick", "kick_off"
    ] = "all"


class SequenceRequest(Filtered):
    pattern_id: Literal[
        "pass_aba", "after_dribble", "turnover_to_shot", "pressure_to_recovery"
    ]


class ZoneRequest(MovementRequest):
    zone_id: Zone = "final_third"


class RankingsRequest(SummaryRequest, Page):
    entity_kind: Literal["team", "player"] = "player"
    metric: Literal[
        "shots",
        "goals",
        "xg",
        "assists",
        "completed_passes",
        "tackles_won",
        "interceptions",
        "dribbles_complete",
        "distance_m",
        "saves",
    ] = "xg"
    min_minutes: Annotated[int, Field(strict=True, ge=0, le=900)] = 0
    normalization: Literal["total", "per90"] = "total"


class SpatialRequest(MatchRequest):
    team_id: Id
    run_id: UUID | None = None
    event_id: UUID | None = None
    period: Literal[1, 2] | None = None
    time_ms: Annotated[int | None, Field(strict=True, ge=0)] = None
    scope: Scope = Field(default_factory=MatchScope)
    epsilon_m: Literal[5, 10, 15, 20] = 15
    view: Literal["summary", "geometry", "matrix", "triangulation"] = "summary"


class ApiResponse(ClosedModel):
    operation_id: str
    method_id: str
    request_id: str
    scope: dict
    data: dict
    provenance: dict
    coverage: dict
    coordinates: dict
    pagination: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
