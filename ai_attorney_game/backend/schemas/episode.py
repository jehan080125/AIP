from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ClickableObject(BaseModel):
    id: str
    evidence_id: str
    label: str
    position: dict[str, float] = Field(default_factory=lambda: {"x": 0, "y": 0})
    image_hint: Optional[str] = None


class EvidenceItem(BaseModel):
    id: str
    name: str
    description: str
    fact: Optional[str] = None
    details: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    public_on_collect: bool = True


class CharacterFile(BaseModel):
    character_id: str
    name: str
    role: str
    description: str = ""
    relation_to_defendant: str = ""
    known_statements: list[str] = Field(default_factory=list)
    credibility_state: str = "unknown"
    portrait: Optional[str] = None
    expression_state: str = "idle"


class TestimonyStatement(BaseModel):
    statement_id: str
    speaker: str
    text: str
    phase: str = "court"


class ContradictionRule(BaseModel):
    rule_id: str
    required_evidence_id: str
    target_statement_id: str
    breakdown_delta: int = 100
    description: str = ""


class BreakdownConditions(BaseModel):
    gauge_threshold: int = 100
    cutscene_id: str = "bd_default"


class CharacterDef(BaseModel):
    id: str
    name: str
    role: str
    portrait_idle: Optional[str] = None
    portrait_breakdown: Optional[str] = None
    portrait_sweat: Optional[str] = None
    description: str = ""
    relation_to_defendant: str = ""
    known_statements: list[str] = Field(default_factory=list)
    credibility_state: str = "unknown"
    portrait: Optional[str] = None
    expression_state: str = "idle"


class ProsecutionClaim(BaseModel):
    claim_id: str
    summary: str
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    supporting_testimony_ids: list[str] = Field(default_factory=list)
    weakness_ids: list[str] = Field(default_factory=list)
    priority: int = 1
    is_core_claim: bool = True


class ProsecutionCase(BaseModel):
    fixed_claim_pool: list[ProsecutionClaim] = Field(default_factory=list)
    allowed_evidence_ids: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    strategy_rules: list[str] = Field(default_factory=list)


class FixedWitnessTestimony(BaseModel):
    statement_id: str
    text: str
    claim_type: str = "identification"
    is_fixed: bool = True


class CoreContradiction(BaseModel):
    contradiction_id: str
    target_claim_id: str
    summary: str
    required_points: list[str] = Field(default_factory=list)
    related_evidence_ids: list[str] = Field(default_factory=list)
    legal_effect: str = ""


class RoundScoringConfig(BaseModel):
    max_score: int = 20
    pass_threshold: int = 14
    core_match_threshold: float = 0.75
    attempt_penalty: int = 2
    hint_penalty: int = 1


class RoundSuccessEffect(BaseModel):
    mark_claim_weakened: Optional[str] = None
    mark_statement_weakened: Optional[str] = None


class RoundFailureEffect(BaseModel):
    attempt_delta: int = 1
    score_penalty: int = 2


class TrialRound(BaseModel):
    round_id: str
    order: int
    active_witness_id: str
    fixed_witness_testimony: FixedWitnessTestimony
    available_claim_ids: list[str] = Field(default_factory=list)
    core_contradictions: list[CoreContradiction] = Field(default_factory=list)
    expected_defense_points: list[str] = Field(default_factory=list)
    related_evidence_ids: list[str] = Field(default_factory=list)
    scoring: RoundScoringConfig = Field(default_factory=RoundScoringConfig)
    hints: list[str] = Field(default_factory=list)
    success_effect: RoundSuccessEffect = Field(default_factory=RoundSuccessEffect)
    failure_effect: RoundFailureEffect = Field(default_factory=RoundFailureEffect)


class StageType(str, Enum):
    VS_WITNESS = "vs_witness"
    VS_PROSECUTOR = "vs_prosecutor"


class StageLifeConfig(BaseModel):
    easy: int = 5
    hard: int = 3


class WitnessTestimonyNode(BaseModel):
    statement_id: str
    text: str
    weakness_id: str
    required_evidence_ids: list[str] = Field(default_factory=list)
    required_logic_points: list[str] = Field(default_factory=list)
    damage_on_success: int = 35
    life_loss_on_fail: int = 1
    counter_statement_id: Optional[str] = None


class WitnessCounterStatement(BaseModel):
    statement_id: str
    text: str
    weakness_id: str
    required_evidence_ids: list[str] = Field(default_factory=list)
    required_logic_points: list[str] = Field(default_factory=list)
    damage_on_success: int = 35
    life_loss_on_fail: int = 1
    next_counter_statement_id: Optional[str] = None


class StageClearCondition(BaseModel):
    witness_mental_lte: Optional[int] = None
    judge_persuasion_gte: Optional[int] = None


class StageScoreConfig(BaseModel):
    max_score: int = 100
    attempt_penalty: int = 8
    life_loss_penalty: int = 10
    hint_penalty: int = 5
    hard_bonus: int = 10


class TrialStage(BaseModel):
    stage_id: str
    stage_type: StageType
    order: int
    active_witness_id: Optional[str] = None
    life: StageLifeConfig = Field(default_factory=StageLifeConfig)
    witness_mental: int = 100
    fixed_testimony_chain: list[WitnessTestimonyNode] = Field(default_factory=list)
    counter_statements: list[WitnessCounterStatement] = Field(default_factory=list)
    clear_condition: StageClearCondition = Field(default_factory=StageClearCondition)
    score_weight: float = 1.0
    hints: list[str] = Field(default_factory=list)
    judge_persuasion: int = 0
    prosecution_claim_pool: list[str] = Field(default_factory=list)
    requires_defense_witness: bool = False
    defense_witnesses: list[str] = Field(default_factory=list)
    summon_witness_action: Optional[dict[str, Any]] = None
    judge_persuasion_threshold: int = 100

    def counter_by_id(self, statement_id: str) -> Optional[WitnessCounterStatement]:
        for stmt in self.counter_statements:
            if stmt.statement_id == statement_id:
                return stmt
        return None

    def testimony_by_id(self, statement_id: str) -> Optional[WitnessTestimonyNode]:
        for stmt in self.fixed_testimony_chain:
            if stmt.statement_id == statement_id:
                return stmt
        return None


class EpisodeTrial(BaseModel):
    trial_id: str
    title: str
    order: int = 1
    stages: list[TrialStage] = Field(default_factory=list)


class EpisodeData(BaseModel):
    episode_id: str
    title: str
    difficulty_available: list[str] = Field(default_factory=lambda: ["easy", "hard"])
    absolute_truth: dict[str, Any]
    scripted_trap: dict[str, Any] = Field(default_factory=dict)
    characters: dict[str, CharacterDef]
    evidences: list[EvidenceItem]
    clickable_objects: list[ClickableObject] = Field(default_factory=list)
    testimony: list[TestimonyStatement] = Field(default_factory=list)
    contradictions: list[ContradictionRule] = Field(default_factory=list)
    breakdown_conditions: BreakdownConditions = Field(default_factory=BreakdownConditions)
    character_knowledge_scope: dict[str, list[str]] = Field(default_factory=dict)
    allowed_lies: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    prosecution_case: Optional[ProsecutionCase] = None
    trial_rounds: list[TrialRound] = Field(default_factory=list)
    trials: list[EpisodeTrial] = Field(default_factory=list)
    character_files: list[CharacterFile] = Field(default_factory=list)

    def get_round(self, round_id: str) -> Optional[TrialRound]:
        for r in self.trial_rounds:
            if r.round_id == round_id:
                return r
        return None

    def get_claim(self, claim_id: str) -> Optional[ProsecutionClaim]:
        if not self.prosecution_case:
            return None
        for c in self.prosecution_case.fixed_claim_pool:
            if c.claim_id == claim_id:
                return c
        return None

    def get_evidence(self, evidence_id: str) -> Optional[EvidenceItem]:
        for e in self.evidences:
            if e.id == evidence_id:
                return e
        return None

    def get_trial(self, trial_id: str) -> Optional[EpisodeTrial]:
        for trial in self.trials:
            if trial.trial_id == trial_id:
                return trial
        return None

    def get_stage(self, stage_id: str) -> Optional[TrialStage]:
        for trial in self.trials:
            for stage in trial.stages:
                if stage.stage_id == stage_id:
                    return stage
        return None

    def first_trial(self) -> Optional[EpisodeTrial]:
        if not self.trials:
            return None
        return sorted(self.trials, key=lambda t: t.order)[0]

    def first_stage(self, trial_id: Optional[str] = None) -> Optional[TrialStage]:
        trial = self.get_trial(trial_id) if trial_id else self.first_trial()
        if not trial or not trial.stages:
            return None
        return sorted(trial.stages, key=lambda s: s.order)[0]

    def next_stage(self, current_stage_id: str) -> Optional[TrialStage]:
        for trial in self.trials:
            stages = sorted(trial.stages, key=lambda s: s.order)
            for idx, stage in enumerate(stages):
                if stage.stage_id == current_stage_id and idx + 1 < len(stages):
                    return stages[idx + 1]
        return None

    def core_claim_ids(self) -> list[str]:
        if not self.prosecution_case:
            return []
        return [c.claim_id for c in self.prosecution_case.fixed_claim_pool if c.is_core_claim]
