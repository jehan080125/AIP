import json
import os
from typing import Any, Optional

from backend.ai_services.openai_structured import parse_openai_structured
from backend.config import LLM_PROVIDER, OPENAI_API_KEY, OPENAI_MODEL
from backend.logging_config import get_logger
from backend.schemas.court import ActorLine, ActorResponse
from backend.schemas.episode import EpisodeData, ProsecutionClaim
from backend.schemas.trial import (
    AnswerEvaluationResult,
    DefenseArgumentEvaluation,
    ProsecutorPlan,
    ProsecutorPlanMode,
)

logger = get_logger(__name__)


class ProsecutorActorLLM:
    def __init__(self, api_key: Optional[str] = None):
        self.openai_api_key = api_key or OPENAI_API_KEY
        self.openai_model = OPENAI_MODEL
        disable_config_llm = api_key is None and bool(os.getenv("PYTEST_CURRENT_TEST"))
        self._use_openai = (
            not disable_config_llm
            and bool(self.openai_api_key)
            and LLM_PROVIDER in ("auto", "openai")
        )

    async def generate(
        self,
        plan: ProsecutorPlan,
        claim: ProsecutionClaim,
        evidence_details: list[dict[str, Any]],
        witness_text: str,
        episode: EpisodeData,
        user_answer: Optional[str] = None,
        evaluation: Optional[AnswerEvaluationResult] = None,
    ) -> ActorResponse:
        import json

        system = (
            "당신은 검사(Prosecutor Actor)입니다. prosecutor_plan의 의미를 바꾸지 마세요. "
            "새 사실·새 증거를 만들지 마세요. forbidden_claims를 말하지 마세요. JSON lines만 반환."
        )
        user = json.dumps(
            {
                "mode": plan.mode.value,
                "plan": plan.model_dump(),
                "claim": claim.model_dump(),
                "evidence_details": evidence_details,
                "witness_text": witness_text,
                "forbidden_claims": episode.prosecution_case.forbidden_claims if episode.prosecution_case else [],
                "user_answer": user_answer,
                "evaluation": evaluation.model_dump() if evaluation else None,
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
                    response_model=ActorResponse,
                    temperature=0.6,
                )
            except Exception as e:
                logger.warning("ProsecutorActor OpenAI failed: %s", e)

        return self._mock(plan, claim, evidence_details, witness_text)

    def _object_particle(self, text: str) -> str:
        stripped = text.strip()
        if not stripped:
            return "을"
        code = ord(stripped[-1])
        if 0xAC00 <= code <= 0xD7A3:
            return "을" if (code - 0xAC00) % 28 else "를"
        return "을"

    def _mock(
        self,
        plan: ProsecutorPlan,
        claim: ProsecutionClaim,
        evidence_details: list[dict],
        witness_text: str,
    ) -> ActorResponse:
        ev_names = ", ".join(e.get("name", "") for e in evidence_details[:2] if e.get("name"))
        evidence_clause = (
            f" 관련 증거로 {ev_names}{self._object_particle(ev_names)} 제시합니다."
            if ev_names
            else ""
        )
        if plan.mode == ProsecutorPlanMode.RETREAT:
            dialogue = f"좋습니다. {claim.summary} 이 주장은 더 이상 강하게 밀어붙이기 어렵겠군요."
            tag = "think"
        elif plan.mode == ProsecutorPlanMode.PRESSURE:
            dialogue = f"변호인, 아직 설명이 부족합니다. {claim.summary}{evidence_clause}"
            tag = "angry"
        elif plan.mode == ProsecutorPlanMode.PIVOT:
            dialogue = f"그렇다면 다른 쟁점으로 넘어가겠습니다. {claim.summary}"
            tag = "objection"
        else:
            if ev_names:
                dialogue = f"검찰은 다음을 주장합니다. {claim.summary}{evidence_clause}"
            else:
                dialogue = f"검찰은 다음을 주장합니다. {claim.summary} 증인 진술을 토대로 말씀드리겠습니다."
            tag = "objection"

        return ActorResponse(
            lines=[ActorLine(speaker="pros_001", dialogue=dialogue, animation_tag=tag)]
        )

    async def generate_stage_pressure(
        self,
        *,
        user_answer: str,
        selected_evidence_ids: list[str],
        selected_evidence_details: list[dict[str, Any]],
        current_statement: Any,
        evaluation: DefenseArgumentEvaluation,
        episode: EpisodeData,
    ) -> ActorResponse:
        import json

        system = (
            "당신은 법정 게임의 검사입니다. 변호인의 반박이 실패했을 때 압박 대사를 만듭니다. "
            "새로운 사실을 만들지 말고, 제공된 증언/증거/평가 결과만 근거로 말하세요. "
            "대사는 한국어로, 1~2줄만 작성하세요. 각 줄은 80자 이하로 하세요. "
            "단조롭게 '부족합니다'만 말하지 말고, 왜 부족한지 논리의 허점을 구체적으로 짚으세요. "
            "말투는 날카롭지만 게임 진행을 돕는 수준이어야 합니다. JSON lines만 반환하세요."
        )
        user = json.dumps(
            {
                "user_answer": user_answer,
                "selected_evidence_ids": selected_evidence_ids,
                "selected_evidence_details": selected_evidence_details,
                "current_statement": current_statement.model_dump()
                if hasattr(current_statement, "model_dump")
                else current_statement,
                "evaluation": evaluation.model_dump(),
                "forbidden_claims": episode.forbidden_claims,
            },
            ensure_ascii=False,
        )

        if self._use_openai:
            try:
                response = await parse_openai_structured(
                    api_key=self.openai_api_key,
                    model=self.openai_model,
                    system=system,
                    user=user,
                    response_model=ActorResponse,
                    temperature=0.75,
                )
                return self._sanitize_pressure_response(response, evaluation, user_answer, selected_evidence_ids)
            except Exception as e:
                logger.warning("Stage ProsecutorActor OpenAI failed: %s", e)

        return self._mock_stage_pressure(evaluation, user_answer, selected_evidence_ids)

    async def generate_stage_interjection(
        self,
        *,
        event_type: str,
        failure_type: str | None = None,
        user_answer: str = "",
        selected_evidence_ids: list[str] | None = None,
        selected_evidence_details: list[dict[str, Any]] | None = None,
        current_statement: Any = None,
        evaluation: DefenseArgumentEvaluation | None = None,
        episode: EpisodeData | None = None,
    ) -> ActorResponse:
        selected_evidence_ids = selected_evidence_ids or []
        selected_evidence_details = selected_evidence_details or []
        if event_type not in {
            "stage_started",
            "irrelevant_answer",
            "no_evidence_selected",
            "witness_rescue",
            "stage_cleared",
        }:
            return ActorResponse(lines=[])

        return self._mock_stage_interjection(
            event_type, failure_type, evaluation, user_answer, selected_evidence_ids
        )

    def _sanitize_pressure_response(
        self,
        response: ActorResponse,
        evaluation: DefenseArgumentEvaluation,
        user_answer: str,
        selected_evidence_ids: list[str],
    ) -> ActorResponse:
        lines = []
        for idx, line in enumerate(response.lines[:2]):
            dialogue = (line.dialogue or "").strip()
            if not dialogue:
                continue
            lines.append(
                ActorLine(
                    speaker="pros_001",
                    dialogue=dialogue[:120],
                    animation_tag=line.animation_tag if line.animation_tag != "idle" else ("angry" if idx == 0 else "think"),
                )
            )
        return ActorResponse(lines=lines) if lines else self._mock_stage_pressure(evaluation, user_answer, selected_evidence_ids)

    def _mock_stage_interjection(
        self,
        event_type: str,
        failure_type: str | None,
        evaluation: DefenseArgumentEvaluation | None,
        user_answer: str,
        selected_evidence_ids: list[str],
    ) -> ActorResponse:
        tag = "angry"
        if event_type == "stage_started":
            dialogue = "검찰은 이 증인의 목격 진술이 피고인의 현장 존재를 뒷받침한다고 봅니다."
            tag = "objection"
        elif event_type == "stage_cleared":
            dialogue = "...이 증언만으로는 더 이상 강하게 주장하기 어렵겠군요."
            tag = "think"
        elif event_type == "witness_rescue":
            dialogue = "증인이 당황한 것과 증언이 거짓이라는 것은 별개의 문제입니다."
            tag = "objection"
        elif failure_type == "no_evidence_selected":
            dialogue = "증거 없는 의혹 제기는 변론이 아닙니다."
        elif failure_type == "irrelevant_answer":
            dialogue = "변호인의 발언은 현재 증언과 무관합니다."
        elif failure_type == "irrelevant_evidence":
            dialogue = "그 증거가 지금 증인의 진술과 어떻게 연결되는지 설명하지 못하고 있습니다."
        elif failure_type == "missing_core_point":
            missing = evaluation.missing_points[0] if evaluation and evaluation.missing_points else "핵심 쟁점"
            dialogue = f"변호인은 {missing} 부분을 비켜갔습니다."
        elif failure_type == "pure_speculation":
            dialogue = "추측만으로는 증인의 진술을 배척할 수 없습니다."
        else:
            dialogue = "주장의 방향은 보입니다만, 증언을 흔들 논리적 연결이 부족합니다."

        return ActorResponse(lines=[ActorLine(speaker="pros_001", dialogue=dialogue, animation_tag=tag)])

    def _mock_stage_pressure(
        self,
        evaluation: DefenseArgumentEvaluation,
        user_answer: str,
        selected_evidence_ids: list[str],
    ) -> ActorResponse:
        no_evidence = not selected_evidence_ids
        short_answer = len(user_answer.strip()) < 18
        missing = [p for p in evaluation.missing_points if p][:1]

        if no_evidence and short_answer:
            lines = [
                "변호인, 인상비평만으로는 증언이 흔들리지 않습니다.",
                "어떤 증거가 어느 부분과 충돌하는지 먼저 연결하십시오.",
            ]
        elif no_evidence:
            lines = [
                "논지는 들었습니다만, 뒷받침할 증거가 없습니다.",
                "증언을 뒤집으려면 기록과 결론을 함께 제시해야 합니다.",
            ]
        elif evaluation.logic_score < 0.45:
            lines = [
                "증거 선택만으로는 부족합니다. 논리의 다리가 빠졌군요.",
                "그 기록이 왜 목격의 신빙성을 낮추는지 설명해야 합니다.",
            ]
        elif evaluation.evidence_usage_score < 0.5:
            lines = [
                "그 증거는 지금 증언의 급소를 직접 찌르지 못합니다.",
                "목격이 왜 불안정한지와 증거를 더 정확히 맞추십시오.",
            ]
        else:
            lines = [
                "아직 핵심 모순을 충분히 찌르지 못했습니다.",
                evaluation.reason or "의심은 있지만, 증언을 무너뜨릴 논증은 아닙니다.",
            ]

        if missing:
            lines[-1] = f"빠진 쟁점은 이것입니다: {missing[0]}"

        return ActorResponse(
            lines=[
                ActorLine(speaker="pros_001", dialogue=lines[0], animation_tag="angry"),
                ActorLine(speaker="pros_001", dialogue=lines[1], animation_tag="think"),
            ]
        )
