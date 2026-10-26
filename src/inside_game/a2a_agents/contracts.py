"""Mensajes A2A de la skill `execute_plan` del agente de datos."""

import json
from typing import Annotated, Literal
from uuid import UUID, uuid4

from a2a.helpers.proto_helpers import get_text_parts, new_text_part
from pydantic import Field

from inside_game.agents.contracts import Evidence, Message

JSON = "application/json"
HTML = "text/html"
EXECUTE_PLAN = "execute_plan"
MAX_PLAN_QUERIES = 60


class PlanQuery(Message):
    key: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")]
    operation: Annotated[str, Field(max_length=80)]
    arguments: dict


class ExecutePlanRequest(Message):
    """Consultas exactas; el agente de datos las ejecuta sin LLM."""

    skill: Literal["execute_plan"] = EXECUTE_PLAN
    request_id: UUID = Field(default_factory=uuid4)
    queries: Annotated[
        list[PlanQuery], Field(min_length=1, max_length=MAX_PLAN_QUERIES)
    ]


class QueryOutcome(Message):
    evidence_ids: list[str] = Field(default_factory=list)
    error: str | None = None


class PlanResult(Message):
    request_id: UUID
    status: Literal["complete", "partial", "error"]
    results: dict[str, QueryOutcome]
    evidence: list[Evidence]


def json_part(model):
    return new_text_part(model.model_dump_json(), media_type=JSON)


def read_json(parts, model):
    """Primer texto JSON de las partes validado contra el contrato."""
    texts = get_text_parts(parts)
    if len(texts) != 1:
        raise ValueError("EXPECTED_ONE_JSON_PART")
    return model.model_validate(json.loads(texts[0]))
