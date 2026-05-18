import os
from typing import Optional

from backend.ai_services.openai_structured import parse_openai_structured
from backend.config import LLM_PROVIDER, OPENAI_API_KEY, OPENAI_MODEL
from backend.logging_config import get_logger
from backend.schemas.episode import (
    EpisodeData,
    ProsecutionClaim,
    TrialRound,
    TrialStage,
    WitnessCounterStatement,
    WitnessTestimonyNode,
)
from backend.schemas.trial import (
    AnswerEvaluationResult,
    AnswerVerdict,
    DefenseArgumentEvaluation,
    ProsecutorPlan,
    RelevanceLevel,
)

logger = get_logger(__name__)


class AnswerEvaluatorLLM:
    def __init__(self, api_key: Optional[str] = None):
        self.openai_api_key = api_key or OPENAI_API_KEY
        self.openai_model = OPENAI_MODEL
        disable_config_llm = api_key is None and bool(os.getenv("PYTEST_CURRENT_TEST"))
        self._use_openai = (
            not disable_config_llm
            and bool(self.openai_api_key)
            and LLM_PROVIDER in ("auto", "openai")
        )

    async def evaluate(
        self,
        user_answer: str,
        selected_evidence_ids: list[str],
        current_round: TrialRound,
        current_plan: ProsecutorPlan,
        selected_claim: ProsecutionClaim,
        episode: EpisodeData,
        attempt_count: int,
        hint_level: int,
    ) -> AnswerEvaluationResult:
        import json

        evidence_details = [
            episode.get_evidence(eid).model_dump()
            for eid in selected_evidence_ids
            if episode.get_evidence(eid)
        ]

        system = (
            "당신은 변호인 답변 평가자입니다. 사건 진실을 새로 만들지 마세요. "
            "현재 검사 주장과 core_contradictions 기준으로 평가하세요. "
            "최종 점수는 계산하지 마세요. JSON만 반환하세요."
        )
        user = json.dumps(
            {
                "user_answer": user_answer,
                "selected_evidence_ids": selected_evidence_ids,
                "evidence_details": evidence_details,
                "current_round": current_round.model_dump(),
                "prosecutor_plan": current_plan.model_dump(),
                "selected_claim": selected_claim.model_dump(),
                "fixed_witness_testimony": current_round.fixed_witness_testimony.model_dump(),
                "attempt_count": attempt_count,
                "hint_level": hint_level,
            },
            ensure_ascii=False,
        )

        if self._use_openai:
            try:
                return await parse_openai_structured(
                    api_key=self.openai_api_key,
                    model=self.openai_model,
                    system=system,
                    user=user,
                    response_model=AnswerEvaluationResult,
                    temperature=0.0,
                )
            except Exception as e:
                logger.warning("AnswerEvaluator OpenAI failed: %s", e)

        return self._mock_evaluate(
            user_answer, selected_evidence_ids, current_round, selected_claim
        )

    async def evaluate_stage_argument(
        self,
        *,
        stage_type: str,
        current_stage: TrialStage,
        current_statement: WitnessTestimonyNode | WitnessCounterStatement,
        user_text: str,
        selected_evidence_ids: list[str],
        selected_evidence_details: list[dict],
        court_records: list[dict],
    ) -> DefenseArgumentEvaluation:
        import json

        system = (
            "당신은 법정 게임의 변호인 주장 평가자입니다. "
            "JSON에 있는 현재 발언의 weakness_id, required_evidence_ids, required_logic_points만 기준으로 평가하세요. "
            "새 사실을 만들지 말고, 점수·생명·스테이지 클리어 여부를 결정하지 마세요. JSON만 반환하세요."
        )
        user = json.dumps(
            {
                "stage_type": stage_type,
                "current_stage": current_stage.model_dump(),
                "current_statement": current_statement.model_dump(),
                "user_text": user_text,
                "selected_evidence_ids": selected_evidence_ids,
                "selected_evidence_details": selected_evidence_details,
                "court_records": court_records,
            },
            ensure_ascii=False,
        )

        if self._use_openai:
            try:
                return await parse_openai_structured(
                    api_key=self.openai_api_key,
                    model=self.openai_model,
                    system=system,
                    user=user,
                    response_model=DefenseArgumentEvaluation,
                    temperature=0.0,
                )
            except Exception as e:
                logger.warning("Stage AnswerEvaluator OpenAI failed: %s", e)

        return self._mock_stage_evaluate(user_text, selected_evidence_ids, current_statement)

    def _mock_evaluate(
        self,
        user_answer: str,
        selected_evidence_ids: list[str],
        current_round: TrialRound,
        selected_claim: ProsecutionClaim,
    ) -> AnswerEvaluationResult:
        text = user_answer.lower()
        expected = [p.lower() for p in current_round.expected_defense_points]
        matched = [p for p in expected if p in text]
        related_ev = set(current_round.related_evidence_ids)
        used_related = bool(related_ev & set(selected_evidence_ids))

        core = current_round.core_contradictions[0] if current_round.core_contradictions else None
        weakness_ids = [core.contradiction_id] if core else []

        keyword_hits = sum(
            1
            for pt in (core.required_points if core else [])
            if any(w in text for w in pt.lower().split()[:3])
        )
        core_match = min(1.0, (len(matched) * 0.2 + keyword_hits * 0.15 + (0.25 if used_related else 0)))

        if not text.strip():
            return AnswerEvaluationResult(
                relevance=RelevanceLevel.IRRELEVANT,
                core_match_score=0.0,
                logic_score=0.0,
                evidence_usage_score=0.0,
                verdict=AnswerVerdict.IRRELEVANT,
                reason="답변이 비어 있습니다.",
            )

        if core_match >= 0.75 and used_related:
            verdict = AnswerVerdict.SUCCESS
        elif core_match >= 0.5:
            verdict = AnswerVerdict.PARTIAL_SUCCESS
        else:
            verdict = AnswerVerdict.FAIL

        return AnswerEvaluationResult(
            relevance=RelevanceLevel.RELEVANT if matched else RelevanceLevel.PARTIALLY_RELEVANT,
            core_match_score=core_match,
            logic_score=min(1.0, core_match + 0.1),
            evidence_usage_score=0.9 if used_related else 0.3,
            matched_points=matched,
            missing_points=[],
            incorrect_points=[],
            attacked_claim_ids=[selected_claim.claim_id],
            matched_weakness_ids=weakness_ids,
            verdict=verdict,
            reason="mock: 키워드·증거 매칭 기반 평가",
        )

    def _mock_stage_evaluate(
        self,
        user_text: str,
        selected_evidence_ids: list[str],
        current_statement: WitnessTestimonyNode | WitnessCounterStatement,
    ) -> DefenseArgumentEvaluation:
        text = user_text.lower()
        required_evidence = set(current_statement.required_evidence_ids)
        selected = set(selected_evidence_ids)
        evidence_hits = required_evidence & selected
        evidence_usage_score = (
            1.0
            if required_evidence and required_evidence.issubset(selected)
            else (len(evidence_hits) / len(required_evidence) if required_evidence else 0.5)
        )

        keyword_bank = {
            "weak_dark_identification": ["가로등", "꺼", "어두", "식별", "신빙", "목격", "정확"],
            "weak_clothes_uncertain": ["처음", "직접", "옷", "체형", "추정", "말", "바뀌"],
            "weak_memory_without_evidence": ["cctv", "다르", "객관", "기억", "증거", "충돌", "특정"],
        }
        keywords = keyword_bank.get(current_statement.weakness_id, [])
        point_keywords = []
        for point in current_statement.required_logic_points:
            for token in point.replace(".", " ").replace(",", " ").split():
                if len(token) >= 2:
                    point_keywords.append(token.lower())
        all_keywords = list(dict.fromkeys(keywords + point_keywords[:12]))
        matched_points = [
            point
            for point in current_statement.required_logic_points
            if any(token in text for token in point.lower().replace(".", " ").split() if len(token) >= 2)
        ]
        keyword_hits = sum(1 for keyword in all_keywords if keyword and keyword in text)
        logic_score = min(1.0, keyword_hits / max(4, min(len(all_keywords), 8)))

        if current_statement.weakness_id == "weak_dark_identification":
            mentions_darkness = any(token in text for token in ("가로등", "꺼", "어두", "조도"))
            attacks_identification = any(token in text for token in ("식별", "정확", "신빙", "목격"))
            if "ev_003" in selected and mentions_darkness and attacks_identification:
                logic_score = max(logic_score, 0.75)
                matched_points = list(current_statement.required_logic_points)

        core_match_score = min(1.0, logic_score * 0.7 + evidence_usage_score * 0.3)

        has_required_evidence = bool(evidence_hits) if required_evidence else bool(selected)

        if not user_text.strip():
            verdict = AnswerVerdict.IRRELEVANT
            relevance = RelevanceLevel.IRRELEVANT
        elif not has_required_evidence and logic_score < 0.2:
            verdict = AnswerVerdict.IRRELEVANT
            relevance = RelevanceLevel.IRRELEVANT
        elif required_evidence and not evidence_hits:
            verdict = AnswerVerdict.FAIL
            relevance = RelevanceLevel.PARTIALLY_RELEVANT
        elif evidence_usage_score >= 0.75 and logic_score >= 0.45:
            verdict = AnswerVerdict.SUCCESS
            relevance = RelevanceLevel.RELEVANT
        elif (evidence_usage_score >= 0.5 and logic_score >= 0.25) or logic_score >= 0.35:
            verdict = AnswerVerdict.PARTIAL_SUCCESS
            relevance = RelevanceLevel.PARTIALLY_RELEVANT
        else:
            verdict = AnswerVerdict.FAIL
            relevance = RelevanceLevel.PARTIALLY_RELEVANT

        missing_points = [
            point for point in current_statement.required_logic_points if point not in matched_points
        ]
        return DefenseArgumentEvaluation(
            relevance=relevance,
            core_match_score=core_match_score,
            logic_score=logic_score,
            evidence_usage_score=evidence_usage_score,
            matched_points=matched_points,
            missing_points=missing_points,
            incorrect_points=[],
            verdict=verdict,
            target_weakness_id=current_statement.weakness_id,
            reason="mock: stage weakness 키워드·증거 매칭 기반 평가",
        )
