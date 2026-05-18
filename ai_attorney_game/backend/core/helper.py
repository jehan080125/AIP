from backend.schemas.episode import TrialRound


class Helper:
    def get_hint(self, current_round: TrialRound, hint_level: int) -> str | None:
        hints = current_round.hints
        if not hints:
            return "증거 상세를 다시 읽고, 검사 주장과 증인 증언의 연결 고리를 찾아보세요."
        if hint_level >= len(hints):
            return hints[-1]
        return hints[hint_level]
