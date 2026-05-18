import json
import os
from typing import Any, Optional

from backend.ai_services.openai_structured import parse_openai_structured
from backend.config import LLM_PROVIDER, OPENAI_API_KEY, OPENAI_MODEL
from backend.logging_config import get_logger
from backend.schemas.court import ActorLine, ActorResponse
from backend.schemas.trial import AnswerVerdict, DefenseArgumentEvaluation, ScoringResult

logger = get_logger(__name__)


class JudgeActorLLM:
    def __init__(self, api_key: Optional[str] = None):
        self.openai_api_key = api_key or OPENAI_API_KEY
        self.openai_model = OPENAI_MODEL
        disable_config_llm = api_key is None and bool(os.getenv("PYTEST_CURRENT_TEST"))
        self._use_openai = (
            not disable_config_llm
            and bool(self.openai_api_key)
            and LLM_PROVIDER in ("auto", "openai")
        )

    async def generate_stage_comment(
        self,
        *,
        stage_type: str,
        event_type: str,
        evaluation: DefenseArgumentEvaluation | dict[str, Any] | None,
        stage_result: dict[str, Any] | None,
        remaining_life: int,
        witness_mental: int | None,
        judge_persuasion: int | None,
        current_statement: dict[str, Any] | None,
        user_answer: str,
        selected_evidence_ids: list[str],
    ) -> ActorResponse:
        parsed_evaluation = self._coerce_evaluation(evaluation)
        payload = {
            "stage_type": stage_type,
            "event_type": event_type,
            "evaluation": parsed_evaluation.model_dump() if parsed_evaluation else evaluation,
            "stage_result": stage_result or {},
            "remaining_life": remaining_life,
            "witness_mental": witness_mental,
            "judge_persuasion": judge_persuasion,
            "current_statement": current_statement or {},
            "user_answer": user_answer,
            "selected_evidence_ids": selected_evidence_ids,
        }
        system = (
            "당신은 법정 게임의 판사입니다. 코드가 이미 정한 evaluation과 stage_result만 "
            "법정 판정문처럼 설명하세요. 생명, 점수, 클리어 여부를 새로 결정하지 마세요. "
            "새 사건 사실이나 새 증거를 만들지 마세요. evaluation.reason을 복붙하지 말고 "
            "자연스럽게 풀어 말하세요. 한국어 1~2줄, 각 줄 90자 이하. JSON lines만 반환하세요."
        )

        if self._use_openai:
            try:
                return self._sanitize(
                    await parse_openai_structured(
                        api_key=self.openai_api_key,
                        model=self.openai_model,
                        system=system,
                        user=json.dumps(payload, ensure_ascii=False),
                        response_model=ActorResponse,
                        temperature=0.35,
                    ),
                    event_type,
                    parsed_evaluation,
                    stage_result,
                    selected_evidence_ids,
                )
            except Exception as e:
                logger.warning("JudgeActor OpenAI failed: %s", e)

        return self._mock_stage_comment(
            event_type, parsed_evaluation, stage_result, selected_evidence_ids
        )

    def final_verdict_lines(
        self,
        verdict: dict,
        weakened_claim_ids: list[str],
    ) -> ActorResponse:
        grade = verdict["grade"]
        total_score = verdict["total_score"]
        max_possible_score = verdict["max_possible_score"]
        score_ratio = verdict["score_ratio"]

        if grade == "S":
            dialogue = "탁월한 변론입니다. 핵심 주장들이 모두 무너졌으므로 완전한 무죄를 선고합니다."
        elif grade == "A":
            dialogue = "설득력 있는 변론입니다. 검사의 주장은 더 이상 유죄를 뒷받침하지 못합니다. 무죄입니다."
        elif grade == "B":
            dialogue = "합리적 의심이 형성되었습니다. 이 법정은 유죄를 단정할 수 없습니다."
        else:
            dialogue = "변론이 불충분합니다. 검사의 핵심 주장을 충분히 흔들지 못했습니다."

        return ActorResponse(
            lines=[
                ActorLine(
                    speaker="judge_001",
                    dialogue=(
                        f"{dialogue} "
                        f"(총점 {total_score}/{max_possible_score}점, "
                        f"달성률 {score_ratio:.0%}, 등급 {grade})"
                    ),
                    animation_tag="idle",
                )
            ]
        )

    def round_comment(self, scoring: ScoringResult) -> ActorResponse:
        if scoring.passed:
            text = f"변론을 인정합니다. 이번 라운드 {scoring.final_score}점."
        else:
            text = f"아직 부족합니다. {scoring.feedback}"
        return ActorResponse(
            lines=[ActorLine(speaker="judge_001", dialogue=text, animation_tag="think")]
        )

    def _coerce_evaluation(
        self, evaluation: DefenseArgumentEvaluation | dict[str, Any] | None
    ) -> DefenseArgumentEvaluation | None:
        if evaluation is None:
            return None
        if isinstance(evaluation, DefenseArgumentEvaluation):
            return evaluation
        return DefenseArgumentEvaluation.model_validate(evaluation)

    def _sanitize(
        self,
        response: ActorResponse,
        event_type: str,
        evaluation: DefenseArgumentEvaluation | None,
        stage_result: dict[str, Any] | None,
        selected_evidence_ids: list[str],
    ) -> ActorResponse:
        lines = []
        for line in response.lines[:2]:
            dialogue = (line.dialogue or "").strip()
            if not dialogue:
                continue
            lines.append(
                ActorLine(
                    speaker="judge_001",
                    dialogue=dialogue[:140],
                    animation_tag=line.animation_tag if line.animation_tag != "idle" else "think",
                )
            )
        if lines:
            return ActorResponse(lines=lines)
        return self._mock_stage_comment(event_type, evaluation, stage_result, selected_evidence_ids)

    def _mock_stage_comment(
        self,
        event_type: str,
        evaluation: DefenseArgumentEvaluation | None,
        stage_result: dict[str, Any] | None,
        selected_evidence_ids: list[str],
    ) -> ActorResponse:
        stage_result = stage_result or {}
        verdict = evaluation.verdict if evaluation else None

        if event_type == "stage_cleared":
            text = "증인의 진술 신빙성은 크게 훼손되었습니다. 이 증언은 더 이상 결정적 근거가 될 수 없습니다."
            tag = "success"
        elif event_type == "stage_failed":
            text = "변호인은 더 이상 이 증언을 다툴 여력을 잃었습니다. 이 스테이지는 실패로 처리합니다."
            tag = "objection"
        elif event_type == "life_lost":
            text = "근거가 약한 주장은 재판을 지연시킬 뿐입니다. 변호인은 신중히 발언하십시오."
            tag = "think"
        elif not selected_evidence_ids:
            text = "변호인, 이 법정은 추측이 아니라 증거에 기반한 주장을 요구합니다."
            tag = "think"
        elif verdict == AnswerVerdict.SUCCESS:
            text = "변호인의 지적은 타당합니다. 제시된 증거는 증인의 진술에 합리적 의문을 일으킵니다."
            tag = "success"
        elif verdict == AnswerVerdict.PARTIAL_SUCCESS:
            text = "방향은 맞습니다. 다만 증거와 진술이 어떻게 충돌하는지 더 명확히 설명해야 합니다."
            tag = "think"
        else:
            text = "변호인의 주장은 현재 증거와 충분히 연결되지 않았습니다. 단순한 의심만으로는 부족합니다."
            tag = "think"

        if stage_result.get("stage_score"):
            text = f"{text} 스테이지 점수는 {stage_result['stage_score']}점입니다."

        return ActorResponse(lines=[ActorLine(speaker="judge_001", dialogue=text, animation_tag=tag)])
