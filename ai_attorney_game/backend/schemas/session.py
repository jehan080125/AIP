from typing import Optional

from pydantic import BaseModel, Field

from backend.schemas.court import CourtRecord, DynamicWeakness


class GamePhase(str):
    INVESTIGATION = "investigation"
    COURT = "court"
    BREAKDOWN = "breakdown"
    TRIAL_FINISHED = "trial_finished"
    ENDED = "ended"


class SessionMeta(BaseModel):
    session_id: str
    episode_id: str
    player_role: str = "defense"
    phase: str = GamePhase.INVESTIGATION
    current_witness: Optional[str] = None
    current_turn: int = 0
    breakdown_gauge: int = 0


class SessionSnapshot(BaseModel):
    meta: SessionMeta
    inventory: list[str] = Field(default_factory=list)
    revealed_evidence: list[str] = Field(default_factory=list)
    court_records: list[CourtRecord] = Field(default_factory=list)
    dynamic_weaknesses: list[DynamicWeakness] = Field(default_factory=list)
    trial_state: Optional[dict] = None
