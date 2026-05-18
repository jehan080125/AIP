from typing import Any, Optional

from backend.schemas.court import ActorResponse, SystemCriticResult, SystemCriticStatus


class SystemCriticLLM:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    async def evaluate(
        self,
        draft: ActorResponse,
        character_contexts: dict[str, dict[str, Any]],
        scripted_trap: str,
        forbidden_claims: list[str],
    ) -> SystemCriticResult:
        return SystemCriticResult(status=SystemCriticStatus.PASS, reason="LLM 미설정 — mock pass")
