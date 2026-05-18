import pytest

from backend.ai_services.prosecutor_planner import ProsecutorPlannerLLM
from backend.core.court_orchestrator import CourtOrchestrator
from backend.core.scoring_engine import compute_final_verdict
from backend.core.state_manager import StateManager
from backend.services.episode_loader import load_episode
from backend.schemas.trial import ProsecutorPlanMode


@pytest.fixture
def episode():
    return load_episode("ep1_tutorial")


@pytest.mark.asyncio
async def test_start_court_starts_first_stage_without_legacy_round(episode):
    state = StateManager()
    court = CourtOrchestrator(state, api_key=None)
    sid = await state.create_session("ep1_tutorial", "defense")
    events = await court.start_court(sid)
    types = [e["type"] for e in events]
    assert "stage_started" in types
    assert "witness_testimony" in types
    assert "round_started" not in types
    assert "prosecutor_response" not in types
    ts = await state.get_trial_state(sid)
    assert ts.current_stage_id == "stage_1_witness_guard"
    assert ts.current_round_id is None


@pytest.mark.asyncio
async def test_witness_testimony_seeded(episode):
    state = StateManager()
    court = CourtOrchestrator(state, api_key=None)
    sid = await state.create_session("ep1_tutorial", "defense")
    await court.start_court(sid)
    records = await state.get_court_records(sid)
    ids = [r.statement_id for r in records]
    assert "stmt_guard_1" in ids


@pytest.mark.asyncio
async def test_planner_only_picks_from_pool(episode):
    planner = ProsecutorPlannerLLM(api_key=None)
    pool_ids = {c.claim_id for c in episode.prosecution_case.fixed_claim_pool}
    plan = await planner.plan(
        episode,
        available_claim_ids=["claim_presence"],
        used_claim_ids=[],
        weakened_claim_ids=[],
    )
    assert plan.selected_claim_id in pool_ids


@pytest.mark.asyncio
async def test_planner_skips_weakened(episode):
    planner = ProsecutorPlannerLLM(api_key=None)
    plan = await planner.plan(
        episode,
        available_claim_ids=["claim_presence", "claim_cctv"],
        used_claim_ids=[],
        weakened_claim_ids=["claim_presence"],
    )
    assert plan.selected_claim_id != "claim_presence"


@pytest.mark.asyncio
async def test_mock_planner_uses_allowed_evidence_only(episode):
    planner = ProsecutorPlannerLLM(api_key=None)
    plan = await planner.plan(
        episode,
        available_claim_ids=["claim_cctv", "claim_motive"],
        used_claim_ids=[],
        weakened_claim_ids=[],
    )
    allowed = set(episode.prosecution_case.allowed_evidence_ids)
    assert set(plan.selected_evidence_ids).issubset(allowed)


@pytest.mark.asyncio
async def test_good_stage_answer_damages_witness_and_gets_judge_comment(episode):
    state = StateManager()
    court = CourtOrchestrator(state, api_key=None)
    sid = await state.create_session("ep1_tutorial", "defense")
    await state.add_evidence(sid, "ev_003")
    await court.start_court(sid)
    events = await court.process_defense_argument(
        sid,
        "stage_1_witness_guard",
        "가로등 정비 기록에 따르면 사건 시각 공원 중앙은 어두웠습니다. 증인이 그 거리에서 피고인을 명확히 식별했다는 목격 신빙성은 낮으며, 단정할 수 없습니다.",
        ["ev_003"],
    )
    types = [e["type"] for e in events]
    assert "defense_argument_evaluated" in types
    assert "judge_comment" in types
    assert "witness_mental_update" in types
    ts = await state.get_trial_state(sid)
    assert ts.witness_mental_by_stage["stage_1_witness_guard"] == 65


@pytest.mark.asyncio
async def test_irrelevant_answer_increments_attempt(episode):
    state = StateManager()
    court = CourtOrchestrator(state, api_key=None)
    sid = await state.create_session("ep1_tutorial", "defense")
    await court.start_court(sid)
    before = (await state.get_trial_state(sid)).stage_attempts.get("stage_1_witness_guard", 0)
    events = await court.process_defense_argument(sid, "stage_1_witness_guard", "오늘 날씨 좋네요", [])
    after = (await state.get_trial_state(sid)).stage_attempts.get("stage_1_witness_guard", 0)
    assert after == before + 1
    types = [e["type"] for e in events]
    assert "defense_argument_evaluated" in types
    assert "judge_comment" in types
    assert "prosecutor_pressure" in types


@pytest.mark.asyncio
async def test_request_hint(episode):
    state = StateManager()
    court = CourtOrchestrator(state, api_key=None)
    sid = await state.create_session("ep1_tutorial", "defense")
    await court.start_court(sid)
    events = await court.request_hint(sid)
    assert events[0]["type"] == "helper_hint"
    assert events[0]["hint_level"] >= 1


def test_final_verdict_uses_score_ratio():
    assert compute_final_verdict(57, 60)["grade"] == "S"
    assert compute_final_verdict(45, 60)["grade"] == "A"
    assert compute_final_verdict(36, 60)["grade"] == "B"
    assert compute_final_verdict(35, 60)["grade"] == "F"


@pytest.mark.asyncio
async def test_full_playthrough_mock(episode):
    state = StateManager()
    court = CourtOrchestrator(state, api_key=None)
    sid = await state.create_session("ep1_tutorial", "defense")
    for eid in ["ev_003", "ev_002", "ev_004", "ev_001"]:
        await state.add_evidence(sid, eid)
    await court.start_court(sid)

    answers = [
        ("가로등이 꺼져 있었다면 증인이 피고인을 정확히 식별했다는 말은 신빙성이 낮습니다.", ["ev_003"]),
        ("처음엔 직접 봤다더니 이제는 옷차림 추정이라고 말이 바뀌었습니다.", ["ev_002", "stmt_guard_1"]),
        ("CCTV 인물은 피고인과 다르니 기억만으로 특정할 수 없습니다.", ["ev_002", "counter_guard_1"]),
    ]
    events = []
    for text, evs in answers:
        events = await court.process_defense_argument(sid, "stage_1_witness_guard", text, evs)
        if any(e.get("type") == "stage_cleared" for e in events):
            break

    await court.summon_defense_witness(sid, "stage_2_vs_prosecutor")
    for _ in range(3):
        events = await court.process_defense_argument(
            sid,
            "stage_2_vs_prosecutor",
            "피고인 신문과 CCTV 기록을 종합하면 검사의 논리는 단정에 가깝습니다.",
            ["stmt_defense_witness_stage_2_vs_prosecutor", "ev_002"],
        )

    ts = await state.get_trial_state(sid)
    meta = await state.get_meta(sid)
    assert meta.phase == "trial_finished"
    assert "stage_1_witness_guard" in ts.cleared_stages
    assert "stage_2_vs_prosecutor" in ts.cleared_stages
    assert any(e.get("type") == "ending" for e in events)
