"""Mensajes del agente de datos; separados de los contratos de consultas SQL.

El solicitante aporta texto y contexto, nunca URL, credenciales ni límites de
ejecución. Las respuestas contienen evidencia copiada del MCP, no cifras del LLM.
"""

from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from inside_game.contracts import ApiResponse, Id, Scope
from inside_game.language import Language


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DataContext(Message):
    match_ids: Annotated[list[Id], Field(max_length=10)] = Field(default_factory=list)
    team_ids: Annotated[list[Id], Field(max_length=20)] = Field(default_factory=list)
    player_ids: Annotated[list[Id], Field(max_length=30)] = Field(default_factory=list)
    event_ids: Annotated[list[UUID], Field(max_length=20)] = Field(default_factory=list)
    scope: Scope | None = None
    sample_step_ms: Literal[200, 1000] | None = None

    @field_validator("sample_step_ms", mode="before")
    @classmethod
    def strict_sampling(cls, value):
        if value is not None and type(value) is not int:
            raise ValueError("sample_step_ms must be a JSON integer")
        return value


class DataRequest(Message):
    request_id: UUID = Field(default_factory=uuid4)
    language: Language = "es"
    original_request: Annotated[str | None, Field(max_length=4000)] = None
    request_text: Annotated[str, Field(min_length=1, max_length=8000)]
    context: DataContext = Field(default_factory=DataContext)

    @field_validator("request_text")
    @classmethod
    def meaningful_text(cls, value):
        if not value.strip():
            raise ValueError("request_text must contain a request")
        return value


class Evidence(Message):
    evidence_id: str
    query_id: str
    operation: str
    arguments: dict
    response: ApiResponse


class AgentIssue(Message):
    code: str
    operation: str | None = None


class DataResult(Message):
    request_id: UUID
    status: Literal[
        "complete", "partial", "needs_clarification", "unsupported", "error"
    ]
    clarification: str | None = None
    # Notas del modelo: orientación de recuperación, no análisis deportivo.
    notes: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    issues: list[AgentIssue] = Field(default_factory=list)
    model: str
    prompt_version: str = "data-agent-2"
    prompt_sha256: str = ""
    tool_calls: int = 0
    model_turns: int = 0
    total_tokens: int = 0
    context_events: list[dict] = Field(default_factory=list)
    tool_trace: list[dict] = Field(default_factory=list)


class FinishRequest(Message):
    """El modelo selecciona evidencia existente; no puede escribir resultados."""

    status: Literal["complete", "partial", "needs_clarification", "unsupported"]
    evidence_ids: Annotated[list[str], Field(max_length=100)]
    clarification: Annotated[str | None, Field(max_length=1000)]
    notes: Annotated[list[Annotated[str, Field(max_length=1000)]], Field(max_length=8)]
