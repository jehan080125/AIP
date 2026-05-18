from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class SpeechAct(str, Enum):
    CONTRADICTION_CLAIM = "contradiction_claim"
    PRESENT_EVIDENCE = "present_evidence"
    FREE_ARGUMENT = "free_argument"
    QUESTION = "question"
    OBJECTION = "objection"
    SMALLTALK = "smalltalk"
    INVALID = "invalid"


class ParsedAction(BaseModel):
    speech_act: SpeechAct
    claim: Optional[str] = None
    used_evidence_id: Optional[str] = None
    target_statement_id: Optional[str] = None
    target_character_id: Optional[str] = None
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class RuleResult(BaseModel):
    success: bool
    matched_rule_id: Optional[str] = None
    reason: str
    state_patch: dict[str, Any] = Field(default_factory=dict)


class ArgumentVerdict(str, Enum):
    VALID_STRONG = "valid_strong"
    VALID_WEAK = "valid_weak"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    IRRELEVANT = "irrelevant"


class ArgumentCriticResult(BaseModel):
    verdict: ArgumentVerdict
    reason: str
    suggested_gauge_delta: int = 0
