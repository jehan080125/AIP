import pytest

from backend.core.court_orchestrator import CourtOrchestrator
from backend.core.state_manager import StateManager


@pytest.mark.asyncio
async def test_stage_flow_with_evidence():
    state = StateManager()
    court = CourtOrchestrator(state, api_key=None)
    session_id = await state.create_session("ep1_tutorial", "defense")
    await state.add_evidence(session_id, "ev_003")
    events = await court.start_court(session_id)
    assert any(e.get("type") == "stage_started" for e in events)
    assert not any(e.get("type") == "round_started" for e in events)

    result = await court.process_defense_argument(
        session_id,
        "stage_1_witness_guard",
        "가로등이 꺼져 공원 중앙이 어두웠으므로 증인의 목격 신빙성이 낮고 식별이 어렵습니다.",
        ["ev_003"],
    )
    assert any(e.get("type") == "defense_argument_evaluated" for e in result)
    assert any(e.get("type") == "judge_comment" for e in result)
