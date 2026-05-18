from typing import Optional

from backend.schemas.actions import ArgumentCriticResult, ArgumentVerdict


class ArgumentCriticLLM:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    async def evaluate(
        self,
        claim: str,
        court_records_text: str,
        inventory_text: str,
        scripted_trap: str,
    ) -> ArgumentCriticResult:
        return ArgumentCriticResult(
            verdict=ArgumentVerdict.UNSUPPORTED,
            reason="LLM 미설정 — 자유 논증은 약한 반응만 허용",
            suggested_gauge_delta=0,
        )
