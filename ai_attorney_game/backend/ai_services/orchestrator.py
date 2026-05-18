"""Backward-compatible wrapper. Use CourtOrchestrator for new code."""

from typing import Any, Optional

from backend.core.court_orchestrator import CourtOrchestrator
from backend.core.state_manager import StateManager
from backend.schemas.payload import PlayerActionPayload


class AIGameOrchestrator:
    def __init__(self, state_manager: StateManager, api_key: Optional[str] = None):
        self._court = CourtOrchestrator(state_manager, api_key=api_key)
        self.state_manager = state_manager

    async def process_turn(self, session_id: str, player_action: PlayerActionPayload) -> dict[str, Any]:
        legacy = {
            "action": player_action.action.value,
            "target": player_action.target,
            "evidence_id": player_action.evidence_id,
            "text": player_action.text,
        }
        if legacy.get("evidence_id") or legacy.get("text"):
            events = await self._court.process_player_answer(
                session_id,
                legacy.get("text") or "",
                [legacy["evidence_id"]] if legacy.get("evidence_id") else [],
            )
        else:
            events = await self._court.process_player_input(session_id, legacy_payload=legacy)

        for ev in events:
            if ev.get("type") == "breakdown":
                lines = ev.get("lines", [])
                text = lines[0].get("dialogue", "") if lines else ""
                return {
                    "status": "breakdown",
                    "speaker": "defendant",
                    "text": f"[anim: breakdown] {text}",
                    "is_breakdown": True,
                    "reason": ev.get("reason", ""),
                }
            if ev.get("type") == "actor_lines":
                lines = ev.get("lines", [])
                if lines:
                    ln = lines[0]
                    tag = ln.get("animation_tag", "idle")
                    dialogue = ln.get("dialogue", "")
                    return {
                        "status": "success",
                        "speaker": ln.get("speaker", "defendant"),
                        "text": f"[anim: {tag}] {dialogue}" if tag != "idle" else dialogue,
                        "is_breakdown": False,
                        "lines": lines,
                    }

        return {"status": "success", "speaker": "system", "text": "", "is_breakdown": False}
