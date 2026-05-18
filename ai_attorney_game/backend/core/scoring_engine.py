from backend.logging_config import get_logger
from backend.schemas.episode import RoundScoringConfig
from backend.schemas.trial import AnswerEvaluationResult, AnswerVerdict, RelevanceLevel, ScoringResult

logger = get_logger(__name__)


def compute_final_verdict(total_score: int, max_possible_score: int) -> dict[str, object]:
    if max_possible_score <= 0:
        score_ratio = 0.0
    else:
        score_ratio = total_score / max_possible_score

    if score_ratio >= 0.90:
        grade = "S"
        label = "S급 변론 / 완전한 무죄 입증"
    elif score_ratio >= 0.75:
        grade = "A"
        label = "A급 변론 / 무죄"
    elif score_ratio >= 0.60:
        grade = "B"
        label = "B급 변론 / 합리적 의심 형성"
    else:
        grade = "F"
        label = "변론 실패"

    return {
        "grade": grade,
        "label": label,
        "score_ratio": round(score_ratio, 4),
        "total_score": total_score,
        "max_possible_score": max_possible_score,
    }


def compute_score(
    round_id: str,
    claim_id: str | None,
    evaluation: AnswerEvaluationResult,
    scoring_cfg: RoundScoringConfig,
    attempt_count: int,
    hint_level: int,
    total_score_before: int,
) -> ScoringResult:
    max_score = scoring_cfg.max_score
    raw = int(
        max_score
        * (
            evaluation.core_match_score * 0.5
            + evaluation.logic_score * 0.25
            + evaluation.evidence_usage_score * 0.25
        )
    )
    attempt_penalty = attempt_count * scoring_cfg.attempt_penalty
    hint_penalty = hint_level * scoring_cfg.hint_penalty
    final_score = max(0, raw - attempt_penalty - hint_penalty)

    passed = (
        evaluation.relevance != RelevanceLevel.IRRELEVANT
        and evaluation.verdict in (AnswerVerdict.SUCCESS, AnswerVerdict.PARTIAL_SUCCESS)
        and evaluation.core_match_score >= scoring_cfg.core_match_threshold
        and final_score >= scoring_cfg.pass_threshold
    )

    total_after = total_score_before + final_score
    feedback = evaluation.reason or (
        "핵심 모순을 효과적으로 지적했습니다." if passed else "주장의 약점을 더 구체적으로 짚어야 합니다."
    )

    logger.info(
        "Scoring round=%s passed=%s raw=%s final=%s total=%s",
        round_id,
        passed,
        raw,
        final_score,
        total_after,
    )

    return ScoringResult(
        round_id=round_id,
        claim_id=claim_id,
        passed=passed,
        raw_score=raw,
        final_score=final_score,
        attempt_penalty=attempt_penalty,
        hint_penalty=hint_penalty,
        total_score_after=total_after,
        feedback=feedback,
    )
