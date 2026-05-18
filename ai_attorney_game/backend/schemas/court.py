from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TruthStatus(str, Enum):
    UNVERIFIED = "unverified"
    CONTRADICTED = "contradicted"
    CONFIRMED = "confirmed"


class CourtRecord(BaseModel):
    statement_id: str
    speaker: str
    text: str
    truth_status: TruthStatus = TruthStatus.UNVERIFIED
    related_facts: list[str] = Field(default_factory=list)
    turn: int = 0
    source: str = "court_dialogue"
    usable_as_evidence: bool = False
    stage_id: Optional[str] = None


class DynamicWeakness(BaseModel):
    id: str
    source_statement_id: str
    possible_contradiction_type: str
    related_evidence_ids: list[str] = Field(default_factory=list)
    description: str


class ActorLine(BaseModel):
    speaker: str
    dialogue: str
    animation_tag: str = "idle"


class ActorResponse(BaseModel):
    lines: list[ActorLine]


class SystemCriticStatus(str, Enum):
    PASS = "pass"
    REJECT = "reject"
    PASS_WITH_DYNAMIC_WEAKNESS = "pass_with_dynamic_weakness"


class SystemCriticResult(BaseModel):
    status: SystemCriticStatus
    reason: str
    dynamic_weakness: Optional[dict[str, Any]] = None
