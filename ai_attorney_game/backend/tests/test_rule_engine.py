import pytest

from backend.core.rule_engine import evaluate
from backend.schemas.actions import ParsedAction, SpeechAct
from backend.schemas.court import CourtRecord
from backend.schemas.episode import BreakdownConditions, ContradictionRule, EpisodeData, EvidenceItem, TestimonyStatement
from backend.schemas.session import SessionMeta, SessionSnapshot


def _episode():
    return EpisodeData(
        episode_id="test",
        title="Test",
        absolute_truth={"description": "test"},
        scripted_trap={"description": "trap"},
        characters={},
        evidences=[
            EvidenceItem(id="ev_003", name="Lamp", description="Bright park"),
        ],
        contradictions=[
            ContradictionRule(
                rule_id="rule_dark_park",
                required_evidence_id="ev_003",
                target_statement_id="stmt_def_alibi",
                breakdown_delta=100,
            )
        ],
        breakdown_conditions=BreakdownConditions(gauge_threshold=100),
        testimony=[
            TestimonyStatement(
                statement_id="stmt_def_alibi",
                speaker="def_001",
                text="It was dark.",
            )
        ],
    )


def _session(inventory=None, court_records=None):
    if court_records is None:
        court_records = [
            CourtRecord(
                statement_id="stmt_def_alibi",
                speaker="def_001",
                text="It was dark.",
            )
        ]
    return SessionSnapshot(
        meta=SessionMeta(session_id="s1", episode_id="test"),
        inventory=inventory if inventory is not None else ["ev_003"],
        court_records=court_records,
    )


def test_rule_success_deterministic():
    ep = _episode()
    sess = _session()
    parsed = ParsedAction(
        speech_act=SpeechAct.PRESENT_EVIDENCE,
        used_evidence_id="ev_003",
        target_statement_id="stmt_def_alibi",
    )
    r1 = evaluate(parsed, ep, sess)
    r2 = evaluate(parsed, ep, sess)
    assert r1 == r2
    assert r1.success is True
    assert r1.matched_rule_id == "rule_dark_park"
    assert r1.state_patch["breakdown_gauge_delta"] == 100


def test_rule_fail_wrong_evidence():
    ep = _episode()
    sess = _session(inventory=["ev_001"], court_records=None)
    parsed = ParsedAction(
        speech_act=SpeechAct.PRESENT_EVIDENCE,
        used_evidence_id="ev_003",
        target_statement_id="stmt_def_alibi",
    )
    r = evaluate(parsed, ep, sess)
    assert r.success is False


def test_rule_fail_missing_statement():
    ep = _episode()
    sess = _session(court_records=[])
    parsed = ParsedAction(
        speech_act=SpeechAct.PRESENT_EVIDENCE,
        used_evidence_id="ev_003",
        target_statement_id="stmt_def_alibi",
    )
    r = evaluate(parsed, ep, sess)
    assert r.success is False
