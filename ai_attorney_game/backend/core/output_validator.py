from backend.schemas.court import ActorLine, ActorResponse
from backend.schemas.episode import EpisodeData

ALLOWED_ANIMATION_TAGS = frozenset(
    {"idle", "breakdown", "sweat", "shake", "angry", "think", "objection"}
)
MAX_DIALOGUE_LEN = 800


class OutputValidator:
    def __init__(self, episode: EpisodeData):
        self.episode = episode
        self.allowed_speakers = {c.id for c in episode.characters.values()}

    def validate(self, response: ActorResponse, allowed_speakers: set[str] | None = None) -> tuple[bool, str]:
        speakers = allowed_speakers or self.allowed_speakers
        if not response.lines:
            return False, "lines가 비어 있습니다."

        for line in response.lines:
            ok, reason = self._validate_line(line, speakers)
            if not ok:
                return False, reason
        return True, "ok"

    def _validate_line(self, line: ActorLine, speakers: set[str]) -> tuple[bool, str]:
        if line.speaker not in speakers:
            return False, f"허용되지 않은 speaker: {line.speaker}"
        if line.animation_tag not in ALLOWED_ANIMATION_TAGS:
            return False, f"허용되지 않은 animation_tag: {line.animation_tag}"
        if not line.dialogue or not line.dialogue.strip():
            return False, "빈 대사입니다."
        if len(line.dialogue) > MAX_DIALOGUE_LEN:
            return False, "대사가 너무 깁니다."
        lower = line.dialogue.lower()
        for forbidden in self.episode.forbidden_claims:
            if forbidden.lower() in lower:
                return False, f"금지 클레임 유출: {forbidden}"
        return True, "ok"
