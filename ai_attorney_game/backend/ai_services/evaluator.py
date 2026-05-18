"""Backward-compatible re-exports."""

from backend.ai_services.argument_critic import ArgumentCriticLLM
from backend.ai_services.system_critic import SystemCriticLLM
from backend.schemas.payload import EvaluatorResultPayload, PlayerAttackResultPayload
from backend.schemas.court import SystemCriticStatus


class LogicEvaluator:
    def __init__(self, api_key: str = "dummy_key"):
        self._system = SystemCriticLLM(api_key)
        self._argument = ArgumentCriticLLM(api_key)

    async def evaluate_draft(
        self, question: str, context: str, draft_answer: str, scripted_trap: str
    ) -> EvaluatorResultPayload:
        from backend.schemas.court import ActorLine, ActorResponse

        draft = ActorResponse(lines=[ActorLine(speaker="def_001", dialogue=draft_answer, animation_tag="idle")])
        result = await self._system.evaluate(draft, {}, scripted_trap, [])
        approved = result.status != SystemCriticStatus.REJECT
        return EvaluatorResultPayload(
            relevance_pass=approved,
            consistency_pass=approved,
            preservation_pass=approved,
            reason=result.reason,
        )

    async def evaluate_player_attack(
        self, presented_evidence: str, defendant_memory: str, scripted_trap: str
    ) -> PlayerAttackResultPayload:
        critic = await self._argument.evaluate(
            presented_evidence, defendant_memory, "", scripted_trap
        )
        from backend.schemas.actions import ArgumentVerdict

        is_bd = critic.verdict == ArgumentVerdict.VALID_STRONG
        return PlayerAttackResultPayload(is_breakdown=is_bd, reason=critic.reason)
