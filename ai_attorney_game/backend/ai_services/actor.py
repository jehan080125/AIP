from typing import Any, Optional

from backend.schemas.court import ActorLine, ActorResponse

SUPPORTED_ACTOR_MODES = {
    "witness_testimony",
    "witness_counter",
    "witness_shaken",
    "witness_breakdown",
    "prosecutor_pressure",
    "judge_comment",
    "helper_hint_reaction",
    "trial_result",
    "episode_ending",
}


class ActorLLM:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    async def generate(
        self,
        scene_type: str,
        speakers: list[str],
        character_contexts: dict[str, dict[str, Any]],
        player_action_summary: str,
        feedback: Optional[str] = None,
    ) -> ActorResponse:
        return self._mock_response(speakers, player_action_summary)

    def _mock_response(self, speakers: list[str], player_action: str) -> ActorResponse:
        speaker = speakers[0] if speakers else "def_001"
        trap = "밤 10시 15분쯤 중앙공원에 산책을 갔지만, 너무 어두워서 시계 바늘도 보이지 않았습니다."
        return ActorResponse(
            lines=[
                ActorLine(
                    speaker=speaker,
                    dialogue=f"(침착하게) {trap} 질문 '{player_action[:40]}'에 대해 부인합니다.",
                    animation_tag="idle",
                )
            ]
        )
