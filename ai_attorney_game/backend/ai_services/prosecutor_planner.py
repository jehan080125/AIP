import os
from typing import Any, Optional

from backend.ai_services.openai_structured import parse_openai_structured
from backend.config import LLM_PROVIDER, OPENAI_API_KEY, OPENAI_MODEL
from backend.logging_config import get_logger
from backend.schemas.episode import EpisodeData, ProsecutionClaim
from backend.schemas.trial import AnswerEvaluationResult, ProsecutorPlan, ProsecutorPlanMode

logger = get_logger(__name__)


class ProsecutorPlannerLLM:
    def __init__(self, api_key: Optional[str] = None):
        self.openai_api_key = api_key or OPENAI_API_KEY
        self.openai_model = OPENAI_MODEL
        disable_config_llm = api_key is None and bool(os.getenv("PYTEST_CURRENT_TEST"))
        self._use_openai = (
            not disable_config_llm
            and bool(self.openai_api_key)
            and LLM_PROVIDER in ("auto", "openai")
        )

    async def plan(
        self,
        episode: EpisodeData,
        available_claim_ids: list[str],
        used_claim_ids: list[str],
        weakened_claim_ids: list[str],
        mode_hint: ProsecutorPlanMode = ProsecutorPlanMode.OPENING,
        last_evaluation: Optional[AnswerEvaluationResult] = None,
        user_answer: Optional[str] = None,
    ) -> ProsecutorPlan:
        pool = episode.prosecution_case.fixed_claim_pool if episode.prosecution_case else []
        allowed_evidence_ids = (
            episode.prosecution_case.allowed_evidence_ids if episode.prosecution_case else []
        )
        candidates = [
            c
            for c in pool
            if c.claim_id in available_claim_ids
            and c.claim_id not in weakened_claim_ids
        ]
        if not candidates and mode_hint not in (ProsecutorPlanMode.RETREAT, ProsecutorPlanMode.PRESSURE):
            candidates = [c for c in pool if c.claim_id not in weakened_claim_ids]

        import json

        system = (
            "당신은 검사 전략 선택기(Prosecutor Planner)입니다. "
            "fixed_claim_pool 안에서만 selected_claim_id를 고르세요. "
            "allowed_evidence_ids 안에서만 증거를 고르세요. "
            "weakened_claim_ids는 다시 선택하지 마세요. JSON만 반환하세요."
        )
        user = json.dumps(
            {
                "fixed_claim_pool": [c.model_dump() for c in pool],
                "available_claim_ids": available_claim_ids,
                "used_claim_ids": used_claim_ids,
                "weakened_claim_ids": weakened_claim_ids,
                "mode_hint": mode_hint.value,
                "last_evaluation": last_evaluation.model_dump() if last_evaluation else None,
                "user_answer": user_answer,
                "strategy_rules": episode.prosecution_case.strategy_rules if episode.prosecution_case else [],
            },
            ensure_ascii=False,
        )

        if self._use_openai:
            try:
                plan = await parse_openai_structured(
                    api_key=self.openai_api_key,
                    model=self.openai_model,
                    system=system,
                    user=user,
                    response_model=ProsecutorPlan,
                    temperature=0.2,
                )
                return self._sanitize_plan(plan, candidates, episode)
            except Exception as e:
                logger.warning("ProsecutorPlanner OpenAI failed: %s", e)

        return self._mock_plan(candidates, mode_hint, last_evaluation, allowed_evidence_ids)

    def _mock_plan(
        self,
        candidates: list[ProsecutionClaim],
        mode_hint: ProsecutorPlanMode,
        last_evaluation: Optional[AnswerEvaluationResult],
        allowed_evidence_ids: list[str],
    ) -> ProsecutorPlan:
        from backend.schemas.trial import AnswerVerdict

        if last_evaluation and last_evaluation.verdict in (
            AnswerVerdict.SUCCESS,
            AnswerVerdict.PARTIAL_SUCCESS,
        ):
            mode = ProsecutorPlanMode.RETREAT
        elif mode_hint == ProsecutorPlanMode.PRESSURE:
            mode = ProsecutorPlanMode.PRESSURE
        else:
            mode = ProsecutorPlanMode.OPENING

        if not candidates:
            return ProsecutorPlan(
                selected_claim_id="",
                selected_evidence_ids=[],
                mode=ProsecutorPlanMode.RETREAT,
                argument_plan=["더 이상 이 쟁점에서 밀어붙일 핵심 주장이 없습니다."],
                reason="mock: no candidates",
            )

        chosen = sorted(candidates, key=lambda c: c.priority)[0]
        allowed = set(allowed_evidence_ids)
        ev_ids = [eid for eid in chosen.supporting_evidence_ids if eid in allowed][:2]
        return ProsecutorPlan(
            selected_claim_id=chosen.claim_id,
            selected_evidence_ids=ev_ids,
            selected_testimony_ids=chosen.supporting_testimony_ids,
            mode=mode,
            argument_plan=[chosen.summary, "제출 증거를 통해 입증하겠습니다."],
            must_include_points=[chosen.summary],
            must_not_say=[],
            reason="mock: highest priority available claim",
        )

    def _sanitize_plan(
        self, plan: ProsecutorPlan, candidates: list[ProsecutionClaim], episode: EpisodeData
    ) -> ProsecutorPlan:
        valid_ids = {c.claim_id for c in candidates}
        ordered_candidates = sorted(candidates, key=lambda c: c.priority)
        if plan.selected_claim_id not in valid_ids and ordered_candidates:
            plan.selected_claim_id = ordered_candidates[0].claim_id
        elif plan.selected_claim_id not in valid_ids:
            plan.selected_claim_id = ""
        allowed = set(episode.prosecution_case.allowed_evidence_ids if episode.prosecution_case else [])
        plan.selected_evidence_ids = [e for e in plan.selected_evidence_ids if e in allowed]
        claim = next((c for c in ordered_candidates if c.claim_id == plan.selected_claim_id), None)
        if claim and not plan.selected_evidence_ids:
            plan.selected_evidence_ids = [e for e in claim.supporting_evidence_ids if e in allowed][:2]
        return plan
