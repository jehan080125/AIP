from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class ActionType(str, Enum):
    QUESTION = "question"
    PRESENT = "present"
    PRESS = "press"


class PlayerActionPayload(BaseModel):
    action: ActionType = Field(..., description="플레이어가 취한 행동의 종류")
    target: str = Field(..., description="행동의 대상")
    evidence_id: Optional[str] = Field(None, description="제시한 증거 ID")
    text: Optional[str] = Field(None, description="플레이어의 추가 발언이나 심문 내용")


class EvaluatorResultPayload(BaseModel):
    relevance_pass: bool = Field(..., description="1차 필터: 질문 부합성")
    consistency_pass: bool = Field(..., description="2차 필터: 의도된 함정 포함 여부")
    preservation_pass: bool = Field(..., description="3차 필터: 환각 방지")
    reason: str = Field(..., description="판독 근거")

    @property
    def is_approved(self) -> bool:
        return self.relevance_pass and self.consistency_pass and self.preservation_pass


class PlayerAttackResultPayload(BaseModel):
    is_breakdown: bool = Field(..., description="논파 성공 여부")
    reason: str = Field(..., description="판독 근거")
