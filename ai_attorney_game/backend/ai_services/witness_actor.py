import json
import os
from typing import Any, Optional

from backend.ai_services.openai_structured import parse_openai_structured
from backend.config import LLM_PROVIDER, OPENAI_API_KEY, OPENAI_MODEL
from backend.logging_config import get_logger
from backend.schemas.court import ActorLine, ActorResponse
from backend.schemas.episode import FixedWitnessTestimony
from backend.schemas.trial import AnswerVerdict, DefenseArgumentEvaluation

logger = get_logger(__name__)


class WitnessActorLLM:
    def __init__(self, api_key: Optional[str] = None):
        self.openai_api_key = api_key or OPENAI_API_KEY
        self.openai_model = OPENAI_MODEL
        disable_config_llm = api_key is None and bool(os.getenv("PYTEST_CURRENT_TEST"))
        self._use_openai = (
            not disable_config_llm
            and bool(self.openai_api_key)
            and LLM_PROVIDER in ("auto", "openai")
        )

    async def speak_testimony(
        self, testimony: FixedWitnessTestimony, witness_id: str, witness_name: str = "증인"
    ) -> ActorResponse:
        return ActorResponse(
            lines=[
                ActorLine(
                    speaker=witness_id,
                    dialogue=testimony.text,
                    animation_tag="idle",
                )
            ]
        )

    async def speak_retreat(
        self, witness_id: str, success: bool = True
    ) -> ActorResponse:
        if success:
            dialogue = "그, 그게... 제가 확신에 차서 말한 건지... 다시 생각해 보니..."
        else:
            dialogue = "저는 본 것이 사실입니다!"
        return ActorResponse(
            lines=[
                ActorLine(
                    speaker=witness_id,
                    dialogue=dialogue,
                    animation_tag="sweat" if success else "angry",
                )
            ]
        )

    async def generate_stage_reaction(
        self,
        *,
        event_type: str,
        witness_id: str,
        evaluation: DefenseArgumentEvaluation | dict[str, Any] | None,
        current_statement: dict[str, Any] | None,
        user_answer: str,
        selected_evidence_ids: list[str],
        witness_mental: int,
        stage_result: dict[str, Any] | None = None,
        next_counter_statement: dict[str, Any] | None = None,
    ) -> ActorResponse:
        if event_type == "witness_counter" and next_counter_statement:
            return ActorResponse(
                lines=[
                    ActorLine(
                        speaker=witness_id,
                        dialogue=next_counter_statement.get("text", ""),
                        animation_tag="angry" if witness_mental <= 65 else "sweat",
                    )
                ]
            )

        parsed_evaluation = self._coerce_evaluation(evaluation)
        payload = {
            "event_type": event_type,
            "evaluation": parsed_evaluation.model_dump() if parsed_evaluation else evaluation,
            "current_statement": current_statement or {},
            "user_answer": user_answer,
            "selected_evidence_ids": selected_evidence_ids,
            "witness_mental": witness_mental,
            "witness_emotion_band": self._emotion_band(witness_mental),
            "stage_result": stage_result or {},
        }
        system = (
            "당신은 법정 게임의 증인입니다. 제공된 current_statement와 evaluation 범위 안에서만 "
            "감정 반응을 말하세요. 새 사실, 새 증거, 자백, JSON에 없는 핵심 증언을 만들지 마세요. "
            "한국어 1줄, 80자 이하. 당황, 반발, 자신감 회복 같은 감정만 표현하세요. JSON lines만 반환하세요."
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
                        temperature=0.65,
                    ),
                    event_type,
                    witness_id,
                    parsed_evaluation,
                    witness_mental,
                )
            except Exception as e:
                logger.warning("WitnessActor OpenAI failed: %s", e)

        return self._mock_stage_reaction(event_type, witness_id, parsed_evaluation, witness_mental)

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
        witness_id: str,
        evaluation: DefenseArgumentEvaluation | None,
        witness_mental: int,
    ) -> ActorResponse:
        lines = []
        for line in response.lines[:1]:
            dialogue = (line.dialogue or "").strip()
            if not dialogue:
                continue
            lines.append(
                ActorLine(
                    speaker=witness_id,
                    dialogue=dialogue[:100],
                    animation_tag=line.animation_tag
                    if line.animation_tag != "idle"
                    else self._animation_for(event_type, evaluation, witness_mental),
                )
            )
        if lines:
            return ActorResponse(lines=lines)
        return self._mock_stage_reaction(event_type, witness_id, evaluation, witness_mental)

    def _mock_stage_reaction(
        self,
        event_type: str,
        witness_id: str,
        evaluation: DefenseArgumentEvaluation | None,
        witness_mental: int,
    ) -> ActorResponse:
        verdict = evaluation.verdict if evaluation else None
        if event_type == "witness_breakdown" or witness_mental <= 0:
            text = "아니야... 그럴 리가 없어... 분명히 설명할 수 있어..."
        elif witness_mental <= 30:
            text = "그만하세요! 저는 거짓말한 게 아닙니다!"
        elif verdict == AnswerVerdict.SUCCESS:
            text = "그, 그건... 제가 본 게 틀렸다는 뜻은 아니잖아요!"
        elif verdict == AnswerVerdict.PARTIAL_SUCCESS:
            text = "그 정도로 제 증언 전체가 틀렸다고 할 수는 없습니다."
        else:
            text = "보셨죠? 변호인도 제 말을 뒤집을 증거는 없는 겁니다."

        return ActorResponse(
            lines=[
                ActorLine(
                    speaker=witness_id,
                    dialogue=text,
                    animation_tag=self._animation_for(event_type, evaluation, witness_mental),
                )
            ]
        )

    def _emotion_band(self, witness_mental: int) -> str:
        if witness_mental <= 0:
            return "breakdown"
        if witness_mental <= 30:
            return "cornered"
        if witness_mental <= 65:
            return "shaken"
        return "annoyed"

    def _animation_for(
        self,
        event_type: str,
        evaluation: DefenseArgumentEvaluation | None,
        witness_mental: int,
    ) -> str:
        if event_type == "witness_breakdown" or witness_mental <= 0:
            return "breakdown"
        if witness_mental <= 30:
            return "angry"
        if evaluation and evaluation.verdict == AnswerVerdict.FAIL:
            return "laugh"
        if evaluation and evaluation.verdict == AnswerVerdict.PARTIAL_SUCCESS:
            return "sweat"
        return "gasp"
