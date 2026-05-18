from typing import Optional

from backend.schemas.actions import ParsedAction, SpeechAct


class InputParserLLM:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    async def parse(self, raw_text: str, session_summary: str = "") -> ParsedAction:
        return self._heuristic_parse(raw_text)

    def _heuristic_parse(self, raw_text: str) -> ParsedAction:
        text = raw_text.strip()
        lower = text.lower()
        evidence_id = None
        for ev in ("ev_001", "ev_002", "ev_003"):
            if ev in text:
                evidence_id = ev
                break

        if evidence_id and any(k in lower for k in ("모순", "맞지", "거짓", "틀렸", "증거")):
            return ParsedAction(
                speech_act=SpeechAct.CONTRADICTION_CLAIM,
                claim=text,
                used_evidence_id=evidence_id,
                target_statement_id="stmt_def_alibi",
                target_character_id="def_001",
                confidence=0.7,
            )
        if evidence_id:
            return ParsedAction(
                speech_act=SpeechAct.PRESENT_EVIDENCE,
                claim=text,
                used_evidence_id=evidence_id,
                confidence=0.7,
            )
        if any(k in lower for k in ("안녕", "뭐야", "ㅋ")):
            return ParsedAction(speech_act=SpeechAct.SMALLTALK, claim=text, confidence=0.9)
        if not text:
            return ParsedAction(speech_act=SpeechAct.INVALID, claim=None, confidence=1.0)
        return ParsedAction(
            speech_act=SpeechAct.QUESTION,
            claim=text,
            target_character_id="def_001",
            confidence=0.6,
        )
