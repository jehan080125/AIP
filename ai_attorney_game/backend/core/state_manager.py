import json
import uuid
from typing import Any, Optional

from backend.config import REDIS_URL, USE_REDIS
from backend.logging_config import get_logger
from backend.schemas.court import CourtRecord, DynamicWeakness, TruthStatus
from backend.schemas.session import GamePhase, SessionMeta, SessionSnapshot
from backend.schemas.trial import ProsecutionClaimState, ProsecutorPlan, TrialState

logger = get_logger(__name__)


class StateManager:
    def __init__(self, redis_url: str = REDIS_URL):
        self._memory: dict[str, dict[str, Any]] = {}
        self._redis = None
        if USE_REDIS:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(redis_url, decode_responses=True)
                logger.info("StateManager using Redis at %s", redis_url)
            except Exception as e:
                logger.warning("Redis unavailable, using in-memory store: %s", e)

    def _key(self, session_id: str, suffix: str) -> str:
        return f"session:{session_id}:{suffix}"

    async def _get_raw(self, session_id: str, suffix: str) -> Optional[str]:
        key = self._key(session_id, suffix)
        if self._redis:
            return await self._redis.get(key)
        store = self._memory.get(session_id, {})
        val = store.get(suffix)
        return json.dumps(val) if val is not None and not isinstance(val, str) else val

    async def _set_raw(self, session_id: str, suffix: str, value: str) -> None:
        key = self._key(session_id, suffix)
        if self._redis:
            await self._redis.set(key, value)
        else:
            self._memory.setdefault(session_id, {})[suffix] = json.loads(value)

    async def create_session(self, episode_id: str, player_role: str = "defense", difficulty: str = "easy") -> str:
        session_id = str(uuid.uuid4())
        meta = SessionMeta(
            session_id=session_id,
            episode_id=episode_id,
            player_role=player_role,
            phase=GamePhase.INVESTIGATION,
            current_turn=0,
            breakdown_gauge=0,
        )
        await self._set_raw(session_id, "meta", meta.model_dump_json())
        await self._set_raw(session_id, "inventory", json.dumps([]))
        await self._set_raw(session_id, "revealed_evidence", json.dumps([]))
        await self._set_raw(session_id, "court_records", json.dumps([]))
        await self._set_raw(session_id, "weaknesses", json.dumps([]))
        await self._set_raw(session_id, "dialogue_temp", json.dumps([]))
        await self._set_raw(
            session_id,
            "trial_state",
            TrialState(
                difficulty=difficulty,
                current_episode_id=episode_id,
                helper_enabled=difficulty == "easy",
            ).model_dump_json(),
        )
        logger.info("Created session %s for episode %s", session_id, episode_id)
        return session_id

    async def get_trial_state(self, session_id: str) -> TrialState:
        raw = await self._get_raw(session_id, "trial_state")
        if not raw:
            ts = TrialState()
            await self._set_raw(session_id, "trial_state", ts.model_dump_json())
            return ts
        return TrialState.model_validate_json(raw)

    async def save_trial_state(self, session_id: str, state: TrialState) -> None:
        await self._set_raw(session_id, "trial_state", state.model_dump_json())

    async def start_episode(self, session_id: str, episode_id: str, difficulty: str) -> TrialState:
        difficulty = difficulty if difficulty in ("easy", "hard") else "easy"
        ts = await self.get_trial_state(session_id)
        ts.difficulty = difficulty
        ts.current_episode_id = episode_id
        ts.helper_enabled = difficulty == "easy"
        ts.current_trial_id = None
        ts.current_stage_id = None
        ts.stage_type = None
        ts.failed_stage_id = None
        await self.save_trial_state(session_id, ts)
        await self.update_meta(session_id, episode_id=episode_id, phase=GamePhase.INVESTIGATION)
        return ts

    async def start_trial(self, session_id: str, trial_id: str) -> TrialState:
        ts = await self.get_trial_state(session_id)
        ts.current_trial_id = trial_id
        ts.failed_stage_id = None
        ts.current_round_id = None
        ts.current_round_index = 0
        ts.current_witness_id = None
        await self.save_trial_state(session_id, ts)
        await self.update_meta(session_id, phase=GamePhase.COURT)
        return ts

    async def start_stage(
        self,
        session_id: str,
        stage_id: str,
        stage_type: str,
        life: int,
        witness_mental: int = 100,
        judge_persuasion: int = 0,
        current_testimony_id: Optional[str] = None,
        active_witness_id: Optional[str] = None,
    ) -> TrialState:
        ts = await self.get_trial_state(session_id)
        ts.current_stage_id = stage_id
        ts.stage_type = stage_type
        ts.stage_life = life
        ts.initial_stage_life.setdefault(stage_id, life)
        ts.life_lost_by_stage.setdefault(stage_id, 0)
        ts.witness_mental_by_stage.setdefault(stage_id, witness_mental)
        ts.judge_persuasion_by_stage.setdefault(stage_id, judge_persuasion)
        ts.current_testimony_id = current_testimony_id
        ts.current_counter_statement_id = None
        ts.stage_attempts.setdefault(stage_id, 0)
        ts.stage_hint_levels.setdefault(stage_id, 0)
        ts.failed_stage_id = None
        await self.save_trial_state(session_id, ts)
        await self.update_meta(session_id, phase=GamePhase.COURT, current_witness=active_witness_id)
        return ts

    async def apply_life_loss(self, session_id: str, amount: int) -> int:
        ts = await self.get_trial_state(session_id)
        stage_id = ts.current_stage_id or ""
        ts.stage_life = max(0, ts.stage_life - max(0, amount))
        if stage_id:
            ts.life_lost_by_stage[stage_id] = ts.life_lost_by_stage.get(stage_id, 0) + max(0, amount)
        await self.save_trial_state(session_id, ts)
        return ts.stage_life

    async def apply_witness_mental_damage(self, session_id: str, stage_id: str, amount: int) -> int:
        ts = await self.get_trial_state(session_id)
        current = ts.witness_mental_by_stage.get(stage_id, 100)
        ts.witness_mental_by_stage[stage_id] = max(0, current - max(0, amount))
        await self.save_trial_state(session_id, ts)
        return ts.witness_mental_by_stage[stage_id]

    async def apply_judge_persuasion(self, session_id: str, stage_id: str, amount: int) -> int:
        ts = await self.get_trial_state(session_id)
        current = ts.judge_persuasion_by_stage.get(stage_id, 0)
        ts.judge_persuasion_by_stage[stage_id] = min(100, current + max(0, amount))
        await self.save_trial_state(session_id, ts)
        return ts.judge_persuasion_by_stage[stage_id]

    async def set_current_statement(
        self,
        session_id: str,
        testimony_id: Optional[str] = None,
        counter_statement_id: Optional[str] = None,
    ) -> TrialState:
        ts = await self.get_trial_state(session_id)
        ts.current_testimony_id = testimony_id
        ts.current_counter_statement_id = counter_statement_id
        await self.save_trial_state(session_id, ts)
        return ts

    async def start_trial_round(self, session_id: str, round_id: str, round_index: int, witness_id: str) -> TrialState:
        ts = await self.get_trial_state(session_id)
        ts.current_round_id = round_id
        ts.current_round_index = round_index
        ts.current_witness_id = witness_id
        ts.round_attempts.setdefault(round_id, 0)
        ts.round_hint_levels.setdefault(round_id, 0)
        ts.awaiting_answer = True
        await self.save_trial_state(session_id, ts)
        await self.update_meta(session_id, current_witness=witness_id)
        return ts

    async def get_current_round_state(self, session_id: str) -> TrialState:
        return await self.get_trial_state(session_id)

    async def set_current_prosecutor_plan(self, session_id: str, plan: ProsecutorPlan) -> None:
        ts = await self.get_trial_state(session_id)
        ts.prosecution_claim_state.current_prosecutor_plan = plan
        ts.prosecution_claim_state.current_claim_id = plan.selected_claim_id
        ts.prosecution_claim_state.current_prosecution_evidence_ids = plan.selected_evidence_ids
        await self.save_trial_state(session_id, ts)

    async def mark_claim_used(self, session_id: str, claim_id: str) -> None:
        ts = await self.get_trial_state(session_id)
        if claim_id not in ts.prosecution_claim_state.used_claim_ids:
            ts.prosecution_claim_state.used_claim_ids.append(claim_id)
        await self.save_trial_state(session_id, ts)

    async def mark_claim_weakened(self, session_id: str, claim_id: str) -> None:
        ts = await self.get_trial_state(session_id)
        pcs = ts.prosecution_claim_state
        if claim_id not in pcs.weakened_claim_ids:
            pcs.weakened_claim_ids.append(claim_id)
        await self.save_trial_state(session_id, ts)

    async def increment_attempt(self, session_id: str, round_id: str) -> int:
        ts = await self.get_trial_state(session_id)
        ts.round_attempts[round_id] = ts.round_attempts.get(round_id, 0) + 1
        await self.save_trial_state(session_id, ts)
        return ts.round_attempts[round_id]

    async def increment_hint_level(self, session_id: str, round_id: str) -> int:
        ts = await self.get_trial_state(session_id)
        ts.round_hint_levels[round_id] = ts.round_hint_levels.get(round_id, 0) + 1
        await self.save_trial_state(session_id, ts)
        return ts.round_hint_levels[round_id]

    async def apply_round_score(self, session_id: str, round_id: str, final_score: int, total_after: int) -> None:
        ts = await self.get_trial_state(session_id)
        ts.round_scores[round_id] = final_score
        ts.total_score = total_after
        await self.save_trial_state(session_id, ts)

    async def mark_round_cleared(self, session_id: str, round_id: str) -> None:
        ts = await self.get_trial_state(session_id)
        if round_id not in ts.cleared_rounds:
            ts.cleared_rounds.append(round_id)
        await self.save_trial_state(session_id, ts)

    async def advance_to_next_round(self, session_id: str, next_round_id: Optional[str], next_index: int, witness_id: Optional[str]) -> TrialState:
        ts = await self.get_trial_state(session_id)
        ts.current_round_id = next_round_id
        ts.current_round_index = next_index
        ts.current_witness_id = witness_id
        ts.awaiting_answer = True
        if next_round_id:
            ts.round_attempts.setdefault(next_round_id, 0)
            ts.round_hint_levels.setdefault(next_round_id, 0)
        await self.save_trial_state(session_id, ts)
        if witness_id:
            await self.update_meta(session_id, current_witness=witness_id)
        return ts

    async def finish_trial(self, session_id: str, verdict: str) -> None:
        ts = await self.get_trial_state(session_id)
        ts.final_verdict_status = verdict
        ts.awaiting_answer = False
        await self.save_trial_state(session_id, ts)
        await self.update_meta(session_id, phase=GamePhase.TRIAL_FINISHED)

    async def init_prosecution_claim_state(self, session_id: str, claim_ids: list[str]) -> None:
        ts = await self.get_trial_state(session_id)
        ts.prosecution_claim_state = ProsecutionClaimState(available_claim_ids=claim_ids)
        await self.save_trial_state(session_id, ts)

    async def mark_statement_weakened(self, session_id: str, statement_id: str) -> None:
        ts = await self.get_trial_state(session_id)
        if statement_id not in ts.weakened_statements:
            ts.weakened_statements.append(statement_id)
        await self.save_trial_state(session_id, ts)
        await self.apply_state_patch(session_id, {"mark_statement_contradicted": statement_id})

    async def get_meta(self, session_id: str) -> SessionMeta:
        raw = await self._get_raw(session_id, "meta")
        if not raw:
            raise KeyError(f"Session not found: {session_id}")
        return SessionMeta.model_validate_json(raw)

    async def update_meta(self, session_id: str, **kwargs: Any) -> SessionMeta:
        meta = await self.get_meta(session_id)
        data = meta.model_dump()
        data.update(kwargs)
        updated = SessionMeta.model_validate(data)
        await self._set_raw(session_id, "meta", updated.model_dump_json())
        return updated

    async def get_inventory(self, session_id: str) -> list[str]:
        raw = await self._get_raw(session_id, "inventory")
        return json.loads(raw or "[]")

    async def add_evidence(self, session_id: str, evidence_id: str) -> list[str]:
        inv = await self.get_inventory(session_id)
        if evidence_id not in inv:
            inv.append(evidence_id)
            await self._set_raw(session_id, "inventory", json.dumps(inv))
            revealed_raw = await self._get_raw(session_id, "revealed_evidence")
            revealed = json.loads(revealed_raw or "[]")
            if evidence_id not in revealed:
                revealed.append(evidence_id)
                await self._set_raw(session_id, "revealed_evidence", json.dumps(revealed))
        logger.info("Session %s collected evidence %s", session_id, evidence_id)
        return inv

    async def get_court_records(self, session_id: str) -> list[CourtRecord]:
        raw = await self._get_raw(session_id, "court_records")
        items = json.loads(raw or "[]")
        return [CourtRecord.model_validate(x) for x in items]

    async def append_court_record(self, session_id: str, record: CourtRecord) -> None:
        records = await self.get_court_records(session_id)
        records = [r for r in records if r.statement_id != record.statement_id]
        records.append(record)
        await self._set_raw(
            session_id, "court_records", json.dumps([r.model_dump() for r in records])
        )

    async def add_court_record(self, session_id: str, record: CourtRecord) -> None:
        await self.append_court_record(session_id, record)

    async def mark_statement_usable_as_evidence(self, session_id: str, statement_id: str) -> None:
        records = await self.get_court_records(session_id)
        updated = []
        for record in records:
            if record.statement_id == statement_id:
                record = record.model_copy(update={"usable_as_evidence": True})
            updated.append(record)
        await self._set_raw(
            session_id, "court_records", json.dumps([r.model_dump() for r in updated])
        )
        ts = await self.get_trial_state(session_id)
        if statement_id not in ts.usable_statement_evidence_ids:
            ts.usable_statement_evidence_ids.append(statement_id)
        await self.save_trial_state(session_id, ts)

    async def clear_stage(self, session_id: str, stage_id: str, stage_score: int = 0) -> None:
        ts = await self.get_trial_state(session_id)
        if stage_id not in ts.cleared_stages:
            ts.cleared_stages.append(stage_id)
        ts.stage_scores[stage_id] = stage_score
        ts.failed_stage_id = None
        await self.save_trial_state(session_id, ts)

    async def fail_stage(self, session_id: str, stage_id: str) -> None:
        ts = await self.get_trial_state(session_id)
        ts.failed_stage_id = stage_id
        await self.save_trial_state(session_id, ts)

    async def restart_stage(self, session_id: str, stage_id: str) -> TrialState:
        ts = await self.get_trial_state(session_id)
        ts.failed_stage_id = None
        ts.stage_life = ts.initial_stage_life.get(stage_id, ts.stage_life)
        ts.life_lost_by_stage[stage_id] = 0
        ts.witness_mental_by_stage[stage_id] = 100
        ts.judge_persuasion_by_stage[stage_id] = 0
        ts.current_counter_statement_id = None
        ts.stage_attempts[stage_id] = 0
        ts.stage_hint_levels[stage_id] = 0
        if stage_id in ts.cleared_stages:
            ts.cleared_stages.remove(stage_id)
        await self.save_trial_state(session_id, ts)
        return ts

    async def calculate_trial_score(self, session_id: str, trial_id: str) -> int:
        ts = await self.get_trial_state(session_id)
        total = sum(ts.stage_scores.values())
        ts.trial_scores[trial_id] = total
        await self.save_trial_state(session_id, ts)
        return total

    async def calculate_episode_score(self, session_id: str, episode_id: str) -> int:
        ts = await self.get_trial_state(session_id)
        ts.episode_total_score = sum(ts.trial_scores.values()) or sum(ts.stage_scores.values())
        await self.save_trial_state(session_id, ts)
        return ts.episode_total_score

    async def get_weaknesses(self, session_id: str) -> list[DynamicWeakness]:
        raw = await self._get_raw(session_id, "weaknesses")
        items = json.loads(raw or "[]")
        return [DynamicWeakness.model_validate(x) for x in items]

    async def add_weakness(self, session_id: str, weakness: DynamicWeakness) -> None:
        items = await self.get_weaknesses(session_id)
        items.append(weakness)
        await self._set_raw(
            session_id, "weaknesses", json.dumps([w.model_dump() for w in items])
        )

    async def apply_state_patch(self, session_id: str, patch: dict[str, Any]) -> SessionMeta:
        meta = await self.get_meta(session_id)
        gauge = meta.breakdown_gauge + patch.get("breakdown_gauge_delta", 0)
        phase = patch.get("phase", meta.phase)
        witness = patch.get("current_witness", meta.current_witness)
        turn = meta.current_turn + patch.get("turn_delta", 0)

        if "mark_statement_contradicted" in patch:
            sid = patch["mark_statement_contradicted"]
            records = await self.get_court_records(session_id)
            updated = []
            for r in records:
                if r.statement_id == sid:
                    r = r.model_copy(update={"truth_status": TruthStatus.CONTRADICTED})
                updated.append(r)
            await self._set_raw(
                session_id, "court_records", json.dumps([r.model_dump() for r in updated])
            )

        return await self.update_meta(
            session_id,
            breakdown_gauge=gauge,
            phase=phase,
            current_witness=witness,
            current_turn=turn,
        )

    async def get_snapshot(self, session_id: str) -> SessionSnapshot:
        meta = await self.get_meta(session_id)
        ts = await self.get_trial_state(session_id)
        return SessionSnapshot(
            meta=meta,
            inventory=await self.get_inventory(session_id),
            revealed_evidence=json.loads(await self._get_raw(session_id, "revealed_evidence") or "[]"),
            court_records=await self.get_court_records(session_id),
            dynamic_weaknesses=await self.get_weaknesses(session_id),
            trial_state=ts.model_dump(),
        )

    async def seed_court_records_from_episode(self, session_id: str, testimony: list) -> None:
        meta = await self.get_meta(session_id)
        for t in testimony:
            record = CourtRecord(
                statement_id=t.statement_id,
                speaker=t.speaker,
                text=t.text,
                turn=meta.current_turn,
            )
            await self.append_court_record(session_id, record)

    # Legacy compatibility
    async def get_current_turn(self, session_id: str) -> int:
        return (await self.get_meta(session_id)).current_turn

    async def increment_turn(self, session_id: str) -> int:
        meta = await self.update_meta(session_id, current_turn=(await self.get_meta(session_id)).current_turn + 1)
        return meta.current_turn

    async def get_player_inventory(self, session_id: str) -> list[str]:
        return await self.get_inventory(session_id)

    async def add_evidence_to_inventory(self, session_id: str, evidence_id: str) -> None:
        await self.add_evidence(session_id, evidence_id)

    async def get_dialogue_history(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        records = await self.get_court_records(session_id)
        tail = records[-limit:]
        return [{"speaker": r.speaker, "text": r.text, "statement_id": r.statement_id} for r in tail]

    async def append_dialogue(self, session_id: str, speaker: str, text: str) -> None:
        meta = await self.get_meta(session_id)
        sid = f"stmt_{speaker}_{meta.current_turn}_{len(await self.get_court_records(session_id))}"
        await self.append_court_record(
            session_id,
            CourtRecord(statement_id=sid, speaker=speaker, text=text, turn=meta.current_turn),
        )
