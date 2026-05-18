import pytest
from pydantic import ValidationError

from backend.core.court_orchestrator import CourtOrchestrator
from backend.core.state_manager import StateManager
from backend.schemas.trial import DefenseArgumentPayload


@pytest.mark.asyncio
async def test_defense_argument_payload_limits():
    with pytest.raises(ValidationError):
        DefenseArgumentPayload(
            session_id="s",
            stage_id="stage",
            text="정상 주장",
            selected_evidence_ids=["ev_001", "ev_002", "ev_003"],
        )

    with pytest.raises(ValidationError):
        DefenseArgumentPayload(
            session_id="s",
            stage_id="stage",
            text="가" * 101,
            selected_evidence_ids=[],
        )


@pytest.mark.asyncio
async def test_easy_and_hard_helper_flags():
    easy_state = StateManager()
    easy_sid = await easy_state.create_session("ep1_tutorial", difficulty="easy")
    easy_court = CourtOrchestrator(easy_state, api_key=None)
    await easy_court.start_court(easy_sid)
    assert (await easy_state.get_trial_state(easy_sid)).helper_enabled is True
    assert (await easy_court.request_hint(easy_sid))[0]["type"] == "helper_hint"

    hard_state = StateManager()
    hard_sid = await hard_state.create_session("ep1_tutorial", difficulty="hard")
    hard_court = CourtOrchestrator(hard_state, api_key=None)
    await hard_court.start_court(hard_sid)
    assert (await hard_state.get_trial_state(hard_sid)).helper_enabled is False
    assert (await hard_court.request_hint(hard_sid))[0]["type"] == "error"


@pytest.mark.asyncio
async def test_vs_witness_success_adds_counter_record_and_damage():
    state = StateManager()
    court = CourtOrchestrator(state, api_key=None)
    sid = await state.create_session("ep1_tutorial", difficulty="easy")
    await court.start_court(sid)

    events = await court.process_defense_argument(
        sid,
        "stage_1_witness_guard",
        "가로등이 꺼져 있었다면 증인이 피고인을 정확히 식별했다는 말은 신빙성이 낮습니다.",
        ["ev_003"],
    )
    ts = await state.get_trial_state(sid)
    assert ts.witness_mental_by_stage["stage_1_witness_guard"] == 65
    assert any(e["type"] == "witness_counter" for e in events)
    assert any(e["type"] == "judge_comment" for e in events)
    assert any(e["type"] in ("witness_reaction", "witness_shaken") for e in events)

    records = await state.get_court_records(sid)
    counter = next(r for r in records if r.statement_id == "counter_guard_1")
    assert counter.usable_as_evidence is True
    assert counter.source == "witness_counter"
    assert "counter_guard_1" in ts.usable_statement_evidence_ids


@pytest.mark.asyncio
async def test_basic_fail_uses_judge_without_default_prosecutor_pressure():
    state = StateManager()
    court = CourtOrchestrator(state, api_key=None)
    sid = await state.create_session("ep1_tutorial", difficulty="easy")
    await court.start_court(sid)

    events = await court.process_defense_argument(
        sid,
        "stage_1_witness_guard",
        "그냥 아닌 것 같습니다.",
        ["ev_003"],
    )
    types = [e["type"] for e in events]
    assert "judge_comment" in types
    assert "life_update" in types
    assert "witness_reaction" in types
    assert "prosecutor_pressure" not in types


@pytest.mark.asyncio
async def test_no_evidence_fail_gets_conditional_prosecutor_pressure():
    state = StateManager()
    court = CourtOrchestrator(state, api_key=None)
    sid = await state.create_session("ep1_tutorial", difficulty="easy")
    await court.start_court(sid)

    events = await court.process_defense_argument(
        sid,
        "stage_1_witness_guard",
        "증인의 말은 그냥 의심스럽습니다.",
        [],
    )
    types = [e["type"] for e in events]
    assert "judge_comment" in types
    assert "prosecutor_pressure" in types


@pytest.mark.asyncio
async def test_vs_witness_fail_loses_life_and_can_fail_stage():
    state = StateManager()
    court = CourtOrchestrator(state, api_key=None)
    sid = await state.create_session("ep1_tutorial", difficulty="hard")
    await court.start_court(sid)

    events = []
    for _ in range(3):
        events = await court.process_defense_argument(
            sid,
            "stage_1_witness_guard",
            "그냥 아닌 것 같습니다.",
            [],
        )

    ts = await state.get_trial_state(sid)
    assert ts.stage_life == 0
    assert ts.failed_stage_id == "stage_1_witness_guard"
    assert any(e["type"] == "stage_failed" for e in events)


@pytest.mark.asyncio
async def test_mock_stage_clear_and_scores_roll_up():
    state = StateManager()
    court = CourtOrchestrator(state, api_key=None)
    sid = await state.create_session("ep1_tutorial", difficulty="easy")
    await court.start_court(sid)

    answers = [
        (
            "가로등이 꺼져 있었다면 증인이 피고인을 정확히 식별했다는 말은 신빙성이 낮습니다.",
            ["ev_003"],
        ),
        (
            "처음엔 직접 봤다더니 이제는 옷차림 추정이라고 말이 바뀌었습니다.",
            ["ev_002", "stmt_guard_1"],
        ),
        (
            "CCTV 인물은 피고인과 다르니 기억만으로 특정할 수 없습니다.",
            ["ev_002", "counter_guard_1"],
        ),
    ]

    events = []
    for text, evidence_ids in answers:
        events = await court.process_defense_argument(
            sid,
            "stage_1_witness_guard",
            text,
            evidence_ids,
        )

    ts = await state.get_trial_state(sid)
    assert "stage_1_witness_guard" in ts.cleared_stages
    assert ts.stage_scores["stage_1_witness_guard"] > 0
    assert any(e["type"] == "stage_cleared" for e in events)
    assert ts.current_stage_id == "stage_2_vs_prosecutor"

    summon_events = await court.summon_defense_witness(sid, "stage_2_vs_prosecutor")
    assert any(e["type"] == "usable_statement_added" for e in summon_events)
    for _ in range(3):
        events = await court.process_defense_argument(
            sid,
            "stage_2_vs_prosecutor",
            "피고인 신문과 기존 증거를 종합하면 검사의 논리는 단정에 가깝습니다.",
            ["stmt_defense_witness_stage_2_vs_prosecutor", "ev_002"],
        )

    ts = await state.get_trial_state(sid)
    assert "stage_2_vs_prosecutor" in ts.cleared_stages
    assert ts.trial_scores["trial_1"] == sum(ts.stage_scores.values())
    assert ts.episode_total_score == ts.trial_scores["trial_1"]
    assert any(e["type"] == "episode_score" for e in events)
    assert any(e["type"] == "ending" for e in events)
