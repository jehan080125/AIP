from backend.logging_config import get_logger
from backend.schemas.actions import ParsedAction, RuleResult, SpeechAct
from backend.schemas.episode import EpisodeData
from backend.schemas.session import SessionSnapshot

logger = get_logger(__name__)


def evaluate(parsed: ParsedAction, episode: EpisodeData, session: SessionSnapshot) -> RuleResult:
    """Deterministic rule evaluation. Same input always yields same output."""
    inventory = set(session.inventory)
    record_ids = {r.statement_id for r in session.court_records}

    evidence_id = parsed.used_evidence_id
    statement_id = parsed.target_statement_id

    if parsed.speech_act in (SpeechAct.CONTRADICTION_CLAIM, SpeechAct.PRESENT_EVIDENCE):
        if not evidence_id:
            return RuleResult(
                success=False,
                reason="증거 ID가 필요합니다.",
                state_patch={},
            )
        if evidence_id not in inventory:
            return RuleResult(
                success=False,
                reason=f"인벤토리에 없는 증거입니다: {evidence_id}",
                state_patch={},
            )

        for rule in episode.contradictions:
            target = statement_id or rule.target_statement_id
            if (
                rule.required_evidence_id == evidence_id
                and rule.target_statement_id == target
                and rule.target_statement_id in record_ids
            ):
                logger.info(
                    "Rule matched: %s (evidence=%s, statement=%s)",
                    rule.rule_id,
                    evidence_id,
                    target,
                )
                return RuleResult(
                    success=True,
                    matched_rule_id=rule.rule_id,
                    reason=rule.description or f"규칙 {rule.rule_id} 충족",
                    state_patch={
                        "breakdown_gauge_delta": rule.breakdown_delta,
                        "mark_statement_contradicted": rule.target_statement_id,
                    },
                )

        return RuleResult(
            success=False,
            reason="일치하는 명시적 모순 규칙이 없습니다.",
            state_patch={},
        )

    return RuleResult(
        success=False,
        reason="Rule Engine 대상이 아닌 speech_act입니다.",
        state_patch={},
    )
