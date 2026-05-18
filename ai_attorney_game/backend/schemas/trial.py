from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ProsecutorPlanMode(str, Enum):
    OPENING = "opening"
    PRESSURE = "pressure"
    PIVOT = "pivot"
    RETREAT = "retreat"


class ProsecutorPlan(BaseModel):
    selected_claim_id: str
    selected_evidence_ids: list[str] = Field(default_factory=list)
    selected_testimony_ids: list[str] = Field(default_factory=list)
    mode: ProsecutorPlanMode = ProsecutorPlanMode.OPENING
    argument_plan: list[str] = Field(default_factory=list)
    must_include_points: list[str] = Field(default_factory=list)
    must_not_say: list[str] = Field(default_factory=list)
    reason: str = ""


class ProsecutionClaimState(BaseModel):
    available_claim_ids: list[str] = Field(default_factory=list)
    used_claim_ids: list[str] = Field(default_factory=list)
    weakened_claim_ids: list[str] = Field(default_factory=list)
    current_claim_id: Optional[str] = None
    current_prosecution_evidence_ids: list[str] = Field(default_factory=list)
    current_prosecutor_plan: Optional[ProsecutorPlan] = None


class AnswerVerdict(str, Enum):
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAIL = "fail"
    IRRELEVANT = "irrelevant"


class RelevanceLevel(str, Enum):
    RELEVANT = "relevant"
    PARTIALLY_RELEVANT = "partially_relevant"
    IRRELEVANT = "irrelevant"


class AnswerEvaluationResult(BaseModel):
    relevance: RelevanceLevel
    core_match_score: float = Field(ge=0.0, le=1.0)
    logic_score: float = Field(ge=0.0, le=1.0)
    evidence_usage_score: float = Field(ge=0.0, le=1.0)
    matched_points: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    incorrect_points: list[str] = Field(default_factory=list)
    attacked_claim_ids: list[str] = Field(default_factory=list)
    matched_weakness_ids: list[str] = Field(default_factory=list)
    verdict: AnswerVerdict
    reason: str = ""


class ScoringResult(BaseModel):
    round_id: str
    claim_id: Optional[str] = None
    passed: bool = False
    raw_score: int = 0
    final_score: int = 0
    attempt_penalty: int = 0
    hint_penalty: int = 0
    total_score_after: int = 0
    feedback: str = ""


class DefenseArgumentPayload(BaseModel):
    session_id: str
    stage_id: str
    text: str = Field(min_length=1, max_length=100)
    selected_evidence_ids: list[str] = Field(default_factory=list, max_length=2)


class DefenseArgumentEvaluation(BaseModel):
    relevance: RelevanceLevel
    core_match_score: float = Field(ge=0.0, le=1.0)
    logic_score: float = Field(ge=0.0, le=1.0)
    evidence_usage_score: float = Field(ge=0.0, le=1.0)
    matched_points: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    incorrect_points: list[str] = Field(default_factory=list)
    verdict: AnswerVerdict
    target_weakness_id: Optional[str] = None
    reason: str = ""


class StageResult(BaseModel):
    stage_id: str
    cleared: bool = False
    failed: bool = False
    remaining_life: int
    stage_score: int = 0
    max_possible_score: int = 100
    score_ratio: float = 0.0
    feedback: str = ""


class TrialScoreResult(BaseModel):
    trial_id: str
    stage_scores: dict[str, int] = Field(default_factory=dict)
    trial_score: int = 0
    max_possible_score: int = 0
    score_ratio: float = 0.0
    verdict_label: str = ""


class EpisodeScoreResult(BaseModel):
    episode_id: str
    trial_scores: dict[str, int] = Field(default_factory=dict)
    episode_score: int = 0
    max_possible_score: int = 0
    score_ratio: float = 0.0
    verdict_label: str = ""
    ending_label: str = ""


class TrialState(BaseModel):
    current_round_id: Optional[str] = None
    current_round_index: int = 0
    current_witness_id: Optional[str] = None
    round_attempts: dict[str, int] = Field(default_factory=dict)
    round_hint_levels: dict[str, int] = Field(default_factory=dict)
    round_scores: dict[str, int] = Field(default_factory=dict)
    total_score: int = 0
    cleared_rounds: list[str] = Field(default_factory=list)
    weakened_statements: list[str] = Field(default_factory=list)
    final_verdict_status: Optional[str] = None
    prosecution_claim_state: ProsecutionClaimState = Field(default_factory=ProsecutionClaimState)
    last_evaluation: Optional[dict[str, Any]] = None
    last_user_answer: Optional[str] = None
    awaiting_answer: bool = True
    difficulty: str = "easy"
    current_episode_id: Optional[str] = None
    current_trial_id: Optional[str] = None
    current_stage_id: Optional[str] = None
    stage_type: Optional[str] = None
    stage_life: int = 0
    initial_stage_life: dict[str, int] = Field(default_factory=dict)
    life_lost_by_stage: dict[str, int] = Field(default_factory=dict)
    witness_mental_by_stage: dict[str, int] = Field(default_factory=dict)
    judge_persuasion_by_stage: dict[str, int] = Field(default_factory=dict)
    current_testimony_id: Optional[str] = None
    current_counter_statement_id: Optional[str] = None
    usable_statement_evidence_ids: list[str] = Field(default_factory=list)
    stage_attempts: dict[str, int] = Field(default_factory=dict)
    stage_hint_levels: dict[str, int] = Field(default_factory=dict)
    stage_scores: dict[str, int] = Field(default_factory=dict)
    trial_scores: dict[str, int] = Field(default_factory=dict)
    episode_total_score: int = 0
    cleared_stages: list[str] = Field(default_factory=list)
    failed_stage_id: Optional[str] = None
    helper_enabled: bool = True
    defense_witness_summoned_by_stage: dict[str, bool] = Field(default_factory=dict)
