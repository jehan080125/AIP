import uuid
from typing import Any, Optional

from backend.ai_services.answer_evaluator import AnswerEvaluatorLLM
from backend.ai_services.input_parser import InputParserLLM
from backend.ai_services.judge_actor import JudgeActorLLM
from backend.ai_services.prosecutor_actor import ProsecutorActorLLM
from backend.ai_services.prosecutor_planner import ProsecutorPlannerLLM
from backend.ai_services.witness_actor import WitnessActorLLM
from backend.core.helper import Helper
from backend.core.scoring_engine import compute_final_verdict, compute_score
from backend.core.stage_engine import StageEngine
from backend.logging_config import get_logger
from backend.schemas.court import CourtRecord, TruthStatus
from backend.schemas.episode import EpisodeData, StageType, TrialRound, TrialStage
from backend.schemas.session import GamePhase
from backend.schemas.trial import (
    AnswerEvaluationResult,
    AnswerVerdict,
    DefenseArgumentEvaluation,
    ProsecutorPlan,
    ProsecutorPlanMode,
)
from backend.core.state_manager import StateManager
from backend.services.episode_loader import load_episode

logger = get_logger(__name__)


class CourtOrchestrator:
    def __init__(self, state_manager: StateManager, api_key: Optional[str] = None):
        self.state = state_manager
        self.planner = ProsecutorPlannerLLM(api_key)
        self.answer_evaluator = AnswerEvaluatorLLM(api_key)
        self.prosecutor_actor = ProsecutorActorLLM(api_key)
        self.witness_actor = WitnessActorLLM(api_key)
        self.judge_actor = JudgeActorLLM(api_key)
        self.helper = Helper()
        self.input_parser = InputParserLLM(api_key)
        self.stage_engine = StageEngine(state_manager, self.answer_evaluator)
        self._episodes: dict[str, EpisodeData] = {}

    def get_episode(self, episode_id: str) -> EpisodeData:
        if episode_id not in self._episodes:
            self._episodes[episode_id] = load_episode(episode_id)
        return self._episodes[episode_id]

    def _character_obj(self, episode: EpisodeData, char_id: str) -> dict:
        for c in episode.characters.values():
            if c.id == char_id:
                return c.model_dump()
        return {"id": char_id, "name": char_id}

    async def start_court(self, session_id: str) -> list[dict[str, Any]]:
        meta = await self.state.get_meta(session_id)
        episode = self.get_episode(meta.episode_id)
        await self.state.update_meta(session_id, phase=GamePhase.COURT)

        if episode.trials:
            first_trial = episode.first_trial()
            if not first_trial:
                return [{"type": "error", "message": "재판 데이터가 없습니다."}]
            return await self.start_trial(session_id, first_trial.trial_id)

        if not episode.trial_rounds or not episode.prosecution_case:
            logger.warning("No trial_rounds; legacy court seed only")
            records = await self.state.get_court_records(session_id)
            if not records and episode.testimony:
                await self.state.seed_court_records_from_episode(session_id, episode.testimony)
            return [{"type": "error", "message": "trial_rounds가 정의되지 않았습니다."}]

        claim_ids = [c.claim_id for c in episode.prosecution_case.fixed_claim_pool]
        await self.state.init_prosecution_claim_state(session_id, claim_ids)

        first = sorted(episode.trial_rounds, key=lambda r: r.order)[0]
        return await self._begin_round(session_id, episode, first)

    async def start_episode(
        self, session_id: str, episode_id: str, difficulty: str = "easy"
    ) -> list[dict[str, Any]]:
        episode = self.get_episode(episode_id)
        if difficulty not in episode.difficulty_available:
            difficulty = "easy"
        await self.state.start_episode(session_id, episode_id, difficulty)
        return [
            {
                "type": "episode_started",
                "episode_id": episode.episode_id,
                "title": episode.title,
                "difficulty": difficulty,
                "helper_enabled": difficulty == "easy",
            }
        ]

    async def _prepare_legacy_round_state(self, session_id: str, episode: EpisodeData) -> None:
        if not episode.trial_rounds or not episode.prosecution_case:
            return
        ts = await self.state.get_trial_state(session_id)
        if ts.current_round_id:
            return
        claim_ids = [c.claim_id for c in episode.prosecution_case.fixed_claim_pool]
        await self.state.init_prosecution_claim_state(session_id, claim_ids)
        first = sorted(episode.trial_rounds, key=lambda r: r.order)[0]
        await self.state.start_trial_round(
            session_id, first.round_id, first.order - 1, first.active_witness_id
        )
        ft = first.fixed_witness_testimony
        await self.state.append_court_record(
            session_id,
            CourtRecord(
                statement_id=ft.statement_id,
                speaker=first.active_witness_id,
                text=ft.text,
                truth_status=TruthStatus.UNVERIFIED,
                source="fixed_testimony",
                usable_as_evidence=True,
            ),
        )
        claim = episode.get_claim(first.available_claim_ids[0]) if first.available_claim_ids else None
        plan = ProsecutorPlan(
            selected_claim_id=claim.claim_id if claim else "",
            selected_evidence_ids=claim.supporting_evidence_ids[:2] if claim else [],
            selected_testimony_ids=claim.supporting_testimony_ids if claim else [],
            mode=ProsecutorPlanMode.OPENING,
            argument_plan=[claim.summary] if claim else [],
            reason="legacy compatibility seed without LLM",
        )
        await self.state.set_current_prosecutor_plan(session_id, plan)
        await self.state.mark_claim_used(session_id, plan.selected_claim_id)

    async def start_trial(self, session_id: str, trial_id: str) -> list[dict[str, Any]]:
        meta = await self.state.get_meta(session_id)
        episode = self.get_episode(meta.episode_id)
        trial = episode.get_trial(trial_id)
        if not trial:
            return [{"type": "error", "message": "재판을 찾을 수 없습니다."}]
        await self.state.start_trial(session_id, trial.trial_id)
        events = [
            {
                "type": "trial_started",
                "trial_id": trial.trial_id,
                "title": trial.title,
                "order": trial.order,
            }
        ]
        first_stage = episode.first_stage(trial.trial_id)
        if first_stage:
            events.extend(await self.start_stage(session_id, first_stage.stage_id))
        return events

    async def _compose_stage_events(
        self,
        session_id: str,
        episode: EpisodeData,
        stage: TrialStage,
        user_answer: str,
        selected_evidence_ids: list[str],
        engine_events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        ts = await self.state.get_trial_state(session_id)
        evaluation_event = next(
            (ev for ev in engine_events if ev.get("type") == "defense_argument_evaluated"),
            None,
        )
        if not evaluation_event:
            return engine_events

        evaluation = DefenseArgumentEvaluation.model_validate(evaluation_event["evaluation"])
        current_statement = evaluation_event.get("current_statement")
        failure_type = evaluation_event.get("failure_type")
        stage_result = next(
            (ev for ev in engine_events if ev.get("type") in ("stage_cleared", "stage_failed")),
            None,
        )
        life_event = next((ev for ev in engine_events if ev.get("type") == "life_update"), None)
        mental_event = next(
            (ev for ev in engine_events if ev.get("type") == "witness_mental_update"),
            None,
        )
        remaining_life = life_event.get("remaining_life", ts.stage_life) if life_event else ts.stage_life
        witness_mental = (
            mental_event.get("remaining_witness_mental")
            if mental_event
            else ts.witness_mental_by_stage.get(stage.stage_id, stage.witness_mental)
        )
        judge_persuasion = ts.judge_persuasion_by_stage.get(stage.stage_id, stage.judge_persuasion)

        if stage_result and stage_result.get("type") == "stage_cleared":
            judge_event_type = "stage_cleared"
        elif stage_result and stage_result.get("type") == "stage_failed":
            judge_event_type = "stage_failed"
        elif life_event:
            judge_event_type = "life_lost"
        elif evaluation.verdict == AnswerVerdict.SUCCESS:
            judge_event_type = "argument_success"
        elif evaluation.verdict == AnswerVerdict.PARTIAL_SUCCESS:
            judge_event_type = "partial_success"
        else:
            judge_event_type = "argument_fail"

        judge = await self.judge_actor.generate_stage_comment(
            stage_type=stage.stage_type.value,
            event_type=judge_event_type,
            evaluation=evaluation,
            stage_result=stage_result,
            remaining_life=remaining_life,
            witness_mental=witness_mental,
            judge_persuasion=judge_persuasion,
            current_statement=current_statement,
            user_answer=user_answer,
            selected_evidence_ids=selected_evidence_ids,
        )

        composed: list[dict[str, Any]] = [evaluation_event]
        composed.append(
            {
                "type": "judge_comment",
                "event_type": judge_event_type,
                "lines": [ln.model_dump() for ln in judge.lines],
                "sfx": "sfx_gavel_3" if judge_event_type in ("stage_cleared", "stage_failed") else "sfx_gavel_1",
                "animation_tag": "success" if judge_event_type == "stage_cleared" else "think",
            }
        )

        if life_event:
            composed.append(life_event)
            prosecutor_event_type = failure_type if failure_type in {
                "no_evidence_selected",
                "irrelevant_answer",
            } else None
            if prosecutor_event_type:
                prosecutor = await self.prosecutor_actor.generate_stage_interjection(
                    event_type=prosecutor_event_type,
                    failure_type=failure_type,
                    user_answer=user_answer,
                    selected_evidence_ids=selected_evidence_ids,
                    selected_evidence_details=evaluation_event.get("selected_evidence_details", []),
                    current_statement=current_statement,
                    evaluation=evaluation,
                    episode=episode,
                )
                if prosecutor.lines:
                    composed.append(
                        {
                            "type": "prosecutor_pressure",
                            "intervention_type": prosecutor_event_type,
                            "failure_type": failure_type,
                            "lines": [ln.model_dump() for ln in prosecutor.lines],
                        }
                    )
            witness = await self.witness_actor.generate_stage_reaction(
                event_type="argument_fail",
                witness_id=stage.active_witness_id or "witness",
                evaluation=evaluation,
                current_statement=current_statement,
                user_answer=user_answer,
                selected_evidence_ids=selected_evidence_ids,
                witness_mental=witness_mental,
                stage_result=stage_result,
            )
            composed.append(
                {
                    "type": "witness_reaction",
                    "stage_id": stage.stage_id,
                    "witness_id": stage.active_witness_id,
                    "lines": [ln.model_dump() for ln in witness.lines],
                }
            )
            if stage_result:
                composed.append(stage_result)
            return composed

        if mental_event:
            if not stage_result:
                witness_event_type = "witness_shaken" if witness_mental <= 65 else "witness_reaction"
                witness = await self.witness_actor.generate_stage_reaction(
                    event_type=witness_event_type,
                    witness_id=stage.active_witness_id or "witness",
                    evaluation=evaluation,
                    current_statement=current_statement,
                    user_answer=user_answer,
                    selected_evidence_ids=selected_evidence_ids,
                    witness_mental=witness_mental,
                    stage_result=stage_result,
                )
                composed.append(
                    {
                        "type": witness_event_type,
                        "stage_id": stage.stage_id,
                        "witness_id": stage.active_witness_id,
                        "witness_mental_band": mental_event.get("witness_mental_band"),
                        "expression_state": mental_event.get("expression_state"),
                        "lines": [ln.model_dump() for ln in witness.lines],
                    }
                )
            composed.append(mental_event)

            if not stage_result and witness_mental <= 30:
                prosecutor = await self.prosecutor_actor.generate_stage_interjection(
                    event_type="witness_rescue",
                    user_answer=user_answer,
                    selected_evidence_ids=selected_evidence_ids,
                    selected_evidence_details=evaluation_event.get("selected_evidence_details", []),
                    current_statement=current_statement,
                    evaluation=evaluation,
                    episode=episode,
                )
                if prosecutor.lines:
                    composed.append(
                        {
                            "type": "prosecutor_pressure",
                            "intervention_type": "witness_rescue",
                            "lines": [ln.model_dump() for ln in prosecutor.lines],
                        }
                    )

        for ev in engine_events:
            ev_type = ev.get("type")
            if ev_type in {
                "defense_argument_evaluated",
                "life_update",
                "witness_mental_update",
                "stage_failed",
            }:
                continue
            if ev_type == "witness_counter":
                counter = await self.witness_actor.generate_stage_reaction(
                    event_type="witness_counter",
                    witness_id=ev.get("witness_id") or stage.active_witness_id or "witness",
                    evaluation=evaluation,
                    current_statement=current_statement,
                    user_answer=user_answer,
                    selected_evidence_ids=selected_evidence_ids,
                    witness_mental=witness_mental,
                    next_counter_statement=ev.get("next_counter_statement"),
                )
                ev = {
                    **ev,
                    "lines": [ln.model_dump() for ln in counter.lines],
                    "sfx": "sfx_gavel_1",
                }
            elif ev_type == "stage_cleared":
                if stage.stage_type == StageType.VS_WITNESS:
                    breakdown = await self.witness_actor.generate_stage_reaction(
                        event_type="witness_breakdown",
                        witness_id=stage.active_witness_id or "witness",
                        evaluation=evaluation,
                        current_statement=current_statement,
                        user_answer=user_answer,
                        selected_evidence_ids=selected_evidence_ids,
                        witness_mental=0,
                        stage_result=ev,
                    )
                    composed.append(
                        {
                            "type": "witness_breakdown",
                            "stage_id": stage.stage_id,
                            "witness_id": stage.active_witness_id,
                            "witness_mental_band": "breakdown",
                            "expression_state": "breakdown",
                            "lines": [ln.model_dump() for ln in breakdown.lines],
                        }
                    )
                prosecutor = await self.prosecutor_actor.generate_stage_interjection(
                    event_type="stage_cleared",
                    current_statement=current_statement,
                    evaluation=evaluation,
                    episode=episode,
                )
                if prosecutor.lines:
                    composed.append(
                        {
                            "type": "prosecutor_pressure",
                            "intervention_type": "stage_cleared",
                            "lines": [ln.model_dump() for ln in prosecutor.lines],
                        }
                    )
            composed.append(ev)

        return composed

    async def start_stage(self, session_id: str, stage_id: str) -> list[dict[str, Any]]:
        meta = await self.state.get_meta(session_id)
        episode = self.get_episode(meta.episode_id)
        stage = episode.get_stage(stage_id)
        if not stage:
            return [{"type": "error", "message": "스테이지를 찾을 수 없습니다."}]
        difficulty = (await self.state.get_trial_state(session_id)).difficulty
        life = stage.life.hard if difficulty == "hard" else stage.life.easy
        first_statement = stage.fixed_testimony_chain[0] if stage.fixed_testimony_chain else None
        await self.state.start_stage(
            session_id,
            stage.stage_id,
            stage.stage_type.value,
            life,
            stage.witness_mental,
            stage.judge_persuasion,
            first_statement.statement_id if first_statement else None,
            stage.active_witness_id,
        )

        events: list[dict[str, Any]] = [
            {
                "type": "stage_started",
                "stage_id": stage.stage_id,
                "stage_type": stage.stage_type.value,
                "order": stage.order,
                "life": life,
                "helper_enabled": difficulty == "easy",
                "active_witness": self._character_obj(episode, stage.active_witness_id)
                if stage.active_witness_id
                else None,
                "witness_mental_band": "steady" if stage.stage_type == StageType.VS_WITNESS else None,
                "judge_persuasion_band": "low" if stage.stage_type == StageType.VS_PROSECUTOR else None,
                "sfx": "sfx_gavel_1",
                "animation_tag": "think",
                "crowd_reaction": "murmur",
            }
        ]

        if stage.stage_type == StageType.VS_WITNESS and first_statement:
            opening = await self.prosecutor_actor.generate_stage_interjection(
                event_type="stage_started",
                current_statement=first_statement,
                episode=episode,
            )
            if opening.lines:
                events.append(
                    {
                        "type": "prosecutor_pressure",
                        "intervention_type": "stage_started",
                        "lines": [ln.model_dump() for ln in opening.lines],
                    }
                )
            await self.state.add_court_record(
                session_id,
                CourtRecord(
                    statement_id=first_statement.statement_id,
                    speaker=stage.active_witness_id or "witness",
                    text=first_statement.text,
                    truth_status=TruthStatus.UNVERIFIED,
                    source="fixed_testimony",
                    usable_as_evidence=True,
                    stage_id=stage.stage_id,
                ),
            )
            await self.state.mark_statement_usable_as_evidence(session_id, first_statement.statement_id)
            events.append(
                {
                    "type": "usable_statement_added",
                    "record": {
                        "statement_id": first_statement.statement_id,
                        "speaker": stage.active_witness_id,
                        "text": first_statement.text,
                        "source": "fixed_testimony",
                        "usable_as_evidence": True,
                        "stage_id": stage.stage_id,
                    },
                }
            )
            events.append(
                {
                    "type": "witness_testimony",
                    "stage_id": stage.stage_id,
                    "statement_id": first_statement.statement_id,
                    "text": first_statement.text,
                    "lines": [
                        {
                            "speaker": stage.active_witness_id or "witness",
                            "dialogue": first_statement.text,
                            "animation_tag": "idle",
                        }
                    ],
                    "sfx": "sfx_gavel_1",
                }
            )
        elif stage.stage_type == StageType.VS_PROSECUTOR:
            events.append(
                {
                    "type": "judge_comment",
                    "lines": [
                        {
                            "speaker": "judge_001",
                            "dialogue": "다음은 검사의 논리 자체를 다투는 절차입니다. 이 부분은 현재 확장 준비 단계입니다.",
                            "animation_tag": "think",
                        }
                    ],
                }
            )
        return events

    async def process_defense_argument(
        self,
        session_id: str,
        stage_id: str,
        text: str,
        selected_evidence_ids: list[str],
    ) -> list[dict[str, Any]]:
        meta = await self.state.get_meta(session_id)
        episode = self.get_episode(meta.episode_id)
        stage = episode.get_stage(stage_id)
        if not stage:
            return [{"type": "error", "message": "스테이지를 찾을 수 없습니다."}]
        engine_events = await self.stage_engine.process_defense_argument(
            session_id, episode, stage, text, selected_evidence_ids
        )
        if engine_events and engine_events[0].get("type") == "error":
            return engine_events
        events = await self._compose_stage_events(
            session_id,
            episode,
            stage,
            text,
            selected_evidence_ids,
            engine_events,
        )
        if any(ev.get("type") == "stage_cleared" for ev in events):
            next_stage = episode.next_stage(stage.stage_id)
            if next_stage:
                events.extend(await self.start_stage(session_id, next_stage.stage_id))
            else:
                ts = await self.state.get_trial_state(session_id)
                trial_id = ts.current_trial_id or (episode.first_trial().trial_id if episode.first_trial() else "trial_1")
                trial_score_result = await self._calculate_trial_score_result(session_id, episode, trial_id)
                episode_score_result = await self._calculate_episode_score_result(session_id, episode)
                await self.state.finish_trial(session_id, episode_score_result["final_verdict"])
                events.append(
                    {
                        "type": "trial_score",
                        "trial_id": trial_id,
                        **trial_score_result,
                        "sfx": "sfx_gavel_3",
                    }
                )
                events.append(
                    {
                        "type": "episode_score",
                        "episode_id": episode.episode_id,
                        **episode_score_result,
                    }
                )
                verdict = {
                    "grade": episode_score_result["final_verdict"],
                    "label": episode_score_result["verdict_label"],
                    "score_ratio": episode_score_result["score_ratio"],
                    "total_score": episode_score_result["episode_score"],
                    "max_possible_score": episode_score_result["max_possible_score"],
                }
                judge = self.judge_actor.final_verdict_lines(verdict, ts.cleared_stages)
                events.append(
                    {
                        "type": "ending",
                        "episode_score": episode_score_result["episode_score"],
                        "max_possible_score": episode_score_result["max_possible_score"],
                        "score_ratio": episode_score_result["score_ratio"],
                        "final_verdict": episode_score_result["final_verdict"],
                        "final_verdict_label": episode_score_result["verdict_label"],
                        "judge_lines": [ln.model_dump() for ln in judge.lines],
                        "lines": [
                            {
                                "speaker": "helper",
                                "dialogue": self._ending_reaction(episode_score_result["score_ratio"]),
                                "animation_tag": "idle",
                            }
                        ],
                        "sfx": "sfx_gavel_3",
                    }
                )
        return events

    async def restart_stage(self, session_id: str, stage_id: str) -> list[dict[str, Any]]:
        await self.state.restart_stage(session_id, stage_id)
        return await self.start_stage(session_id, stage_id)

    async def summon_defense_witness(self, session_id: str, stage_id: str) -> list[dict[str, Any]]:
        meta = await self.state.get_meta(session_id)
        episode = self.get_episode(meta.episode_id)
        stage = episode.get_stage(stage_id)
        if not stage or stage.stage_type != StageType.VS_PROSECUTOR:
            return [{"type": "error", "message": "이 스테이지에서는 변호인측 증인을 소환할 수 없습니다."}]
        ts = await self.state.get_trial_state(session_id)
        ts.defense_witness_summoned_by_stage[stage.stage_id] = True
        await self.state.save_trial_state(session_id, ts)
        witness_id = stage.defense_witnesses[0] if stage.defense_witnesses else "def_001"
        statement_id = f"stmt_defense_witness_{stage.stage_id}"
        text = "저는 사건 시각 현장에 없었습니다. 검사의 주장은 정황을 너무 단정하고 있습니다."
        await self.state.add_court_record(
            session_id,
            CourtRecord(
                statement_id=statement_id,
                speaker=witness_id,
                text=text,
                truth_status=TruthStatus.UNVERIFIED,
                source="defense_witness",
                usable_as_evidence=True,
                stage_id=stage.stage_id,
            ),
        )
        await self.state.mark_statement_usable_as_evidence(session_id, statement_id)
        return [
            {
                "type": "usable_statement_added",
                "record": {
                    "statement_id": statement_id,
                    "speaker": witness_id,
                    "text": text,
                    "source": "defense_witness",
                    "usable_as_evidence": True,
                    "stage_id": stage.stage_id,
                },
            },
            {
                "type": "witness_testimony",
                "stage_id": stage.stage_id,
                "statement_id": statement_id,
                "text": text,
                "lines": [
                    {
                        "speaker": witness_id,
                        "dialogue": text,
                        "animation_tag": "serious",
                    }
                ],
                "sfx": "sfx_gavel_1",
            },
            {
                "type": "judge_comment",
                "event_type": "defense_witness_summoned",
                "lines": [
                    {
                        "speaker": "judge_001",
                        "dialogue": "변호인측 증인의 발언을 기록합니다. 이제 이 진술을 근거로 검사의 논리를 다툴 수 있습니다.",
                        "animation_tag": "think",
                    }
                ],
                "sfx": "sfx_gavel_1",
            },
        ]

    async def _begin_round(
        self, session_id: str, episode: EpisodeData, round_def: TrialRound
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        await self.state.start_trial_round(
            session_id, round_def.round_id, round_def.order - 1, round_def.active_witness_id
        )

        ft = round_def.fixed_witness_testimony
        await self.state.append_court_record(
            session_id,
            CourtRecord(
                statement_id=ft.statement_id,
                speaker=round_def.active_witness_id,
                text=ft.text,
                truth_status=TruthStatus.UNVERIFIED,
            ),
        )

        witness_lines = await self.witness_actor.speak_testimony(
            ft, round_def.active_witness_id
        )
        events.append({"type": "witness_testimony", "lines": [ln.model_dump() for ln in witness_lines.lines]})

        ts = await self.state.get_trial_state(session_id)
        plan = await self.planner.plan(
            episode,
            available_claim_ids=round_def.available_claim_ids,
            used_claim_ids=ts.prosecution_claim_state.used_claim_ids,
            weakened_claim_ids=ts.prosecution_claim_state.weakened_claim_ids,
            mode_hint=ProsecutorPlanMode.OPENING,
        )
        await self.state.set_current_prosecutor_plan(session_id, plan)
        await self.state.mark_claim_used(session_id, plan.selected_claim_id)

        events.append(
            {
                "type": "prosecutor_plan",
                "selected_claim_id": plan.selected_claim_id,
                "selected_evidence_ids": plan.selected_evidence_ids,
                "mode": plan.mode.value,
                "argument_plan": plan.argument_plan,
            }
        )

        claim = episode.get_claim(plan.selected_claim_id)
        ev_details = [
            episode.get_evidence(eid).model_dump()
            for eid in plan.selected_evidence_ids
            if episode.get_evidence(eid)
        ]
        pros = await self.prosecutor_actor.generate(
            plan, claim, ev_details, ft.text, episode
        )
        for ln in pros.lines:
            await self.state.append_court_record(
                session_id,
                CourtRecord(
                    statement_id=f"stmt_pros_{uuid.uuid4().hex[:6]}",
                    speaker=ln.speaker,
                    text=ln.dialogue,
                ),
            )

        events.append(
            {
                "type": "round_started",
                "round_id": round_def.round_id,
                "round_index": round_def.order,
                "active_witness": self._character_obj(episode, round_def.active_witness_id),
                "fixed_witness_testimony": ft.model_dump(),
                "available_claim_ids": round_def.available_claim_ids,
                "related_evidence_ids": round_def.related_evidence_ids,
                "current_claim": claim.model_dump() if claim else None,
            }
        )
        events.append(
            {
                "type": "prosecutor_response",
                "mode": plan.mode.value,
                "lines": [ln.model_dump() for ln in pros.lines],
            }
        )
        return events

    async def process_player_answer(
        self,
        session_id: str,
        text: str,
        selected_evidence_ids: list[str],
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        meta = await self.state.get_meta(session_id)
        episode = self.get_episode(meta.episode_id)
        ts = await self.state.get_trial_state(session_id)

        if meta.phase == GamePhase.TRIAL_FINISHED:
            return [{"type": "error", "message": "재판이 이미 종료되었습니다."}]

        if not ts.current_round_id:
            return await self.start_court(session_id)

        round_def = episode.get_round(ts.current_round_id)
        if not round_def:
            return [{"type": "error", "message": "현재 라운드를 찾을 수 없습니다."}]

        plan = ts.prosecution_claim_state.current_prosecutor_plan
        if not plan:
            return [{"type": "error", "message": "검사 주장 계획이 없습니다."}]

        claim = episode.get_claim(plan.selected_claim_id)
        if not claim:
            return [{"type": "error", "message": "현재 주장을 찾을 수 없습니다."}]

        await self.state.append_dialogue(session_id, speaker="player", text=text)
        ts.last_user_answer = text
        attempt = ts.round_attempts.get(round_def.round_id, 0)
        hint_level = ts.round_hint_levels.get(round_def.round_id, 0)

        evaluation = await self.answer_evaluator.evaluate(
            text, selected_evidence_ids, round_def, plan, claim, episode, attempt, hint_level
        )
        ts.last_evaluation = evaluation.model_dump()
        await self.state.save_trial_state(session_id, ts)

        scoring = compute_score(
            round_def.round_id,
            plan.selected_claim_id,
            evaluation,
            round_def.scoring,
            attempt,
            hint_level,
            ts.total_score,
        )
        await self.state.apply_round_score(
            session_id, round_def.round_id, scoring.final_score, scoring.total_score_after
        )

        judge_lines = self.judge_actor.round_comment(scoring)
        events.append(
            {
                "type": "answer_evaluated",
                "evaluation": evaluation.model_dump(),
                "scoring": scoring.model_dump(),
                "passed": scoring.passed,
            }
        )
        events.append(
            {
                "type": "judge_comment",
                "lines": [ln.model_dump() for ln in judge_lines.lines],
            }
        )

        if scoring.passed:
            if round_def.success_effect.mark_claim_weakened:
                await self.state.mark_claim_weakened(
                    session_id, round_def.success_effect.mark_claim_weakened
                )
                events.append(
                    {
                        "type": "claim_weakened",
                        "claim_id": round_def.success_effect.mark_claim_weakened,
                        "weakness_ids": evaluation.matched_weakness_ids,
                    }
                )
            if round_def.success_effect.mark_statement_weakened:
                await self.state.mark_statement_weakened(
                    session_id, round_def.success_effect.mark_statement_weakened
                )
            retreat = await self.witness_actor.speak_retreat(
                round_def.active_witness_id, success=True
            )
            events.append(
                {"type": "witness_reaction", "lines": [ln.model_dump() for ln in retreat.lines]}
            )

            retreat_plan = await self.planner.plan(
                episode,
                round_def.available_claim_ids,
                ts.prosecution_claim_state.used_claim_ids,
                (await self.state.get_trial_state(session_id)).prosecution_claim_state.weakened_claim_ids,
                mode_hint=ProsecutorPlanMode.RETREAT,
                last_evaluation=evaluation,
                user_answer=text,
            )
            pros = await self.prosecutor_actor.generate(
                retreat_plan,
                claim,
                [],
                round_def.fixed_witness_testimony.text,
                episode,
                text,
                evaluation,
            )
            events.append(
                {
                    "type": "prosecutor_response",
                    "mode": "retreat",
                    "lines": [ln.model_dump() for ln in pros.lines],
                }
            )

            await self.state.mark_round_cleared(session_id, round_def.round_id)
            events.append(
                {
                    "type": "round_cleared",
                    "round_id": round_def.round_id,
                    "score": scoring.final_score,
                }
            )

            if await self._all_core_claims_weakened(session_id, episode):
                events.extend(await self._finish_trial(session_id, episode))
            else:
                nxt = self._next_round(episode, round_def)
                if nxt:
                    events[-1]["next_round_id"] = nxt.round_id
                    events.extend(await self._begin_round(session_id, episode, nxt))
                else:
                    events.extend(await self._finish_trial(session_id, episode))
        else:
            await self.state.increment_attempt(session_id, round_def.round_id)
            pressure_plan = await self.planner.plan(
                episode,
                round_def.available_claim_ids,
                ts.prosecution_claim_state.used_claim_ids,
                ts.prosecution_claim_state.weakened_claim_ids,
                mode_hint=ProsecutorPlanMode.PRESSURE,
                last_evaluation=evaluation,
                user_answer=text,
            )
            await self.state.set_current_prosecutor_plan(session_id, pressure_plan)
            ev_details = [
                episode.get_evidence(eid).model_dump()
                for eid in pressure_plan.selected_evidence_ids
                if episode.get_evidence(eid)
            ]
            pressure_claim = episode.get_claim(pressure_plan.selected_claim_id) or claim
            pros = await self.prosecutor_actor.generate(
                pressure_plan,
                pressure_claim,
                ev_details,
                round_def.fixed_witness_testimony.text,
                episode,
                text,
                evaluation,
            )
            events.append(
                {
                    "type": "prosecutor_response",
                    "mode": "pressure",
                    "lines": [ln.model_dump() for ln in pros.lines],
                }
            )

        return events

    async def request_hint(self, session_id: str) -> list[dict[str, Any]]:
        meta = await self.state.get_meta(session_id)
        episode = self.get_episode(meta.episode_id)
        ts = await self.state.get_trial_state(session_id)
        if ts.current_stage_id:
            if not ts.helper_enabled:
                return [{"type": "error", "message": "hard mode에서는 힌트를 사용할 수 없습니다."}]
            stage = episode.get_stage(ts.current_stage_id)
            if not stage:
                return [{"type": "error", "message": "스테이지를 찾을 수 없습니다."}]
            ts.stage_hint_levels[stage.stage_id] = ts.stage_hint_levels.get(stage.stage_id, 0) + 1
            await self.state.save_trial_state(session_id, ts)
            level = ts.stage_hint_levels[stage.stage_id]
            hints = stage.hints or ["현재 발언과 증거의 연결을 다시 보십시오."]
            hint = hints[min(level - 1, len(hints) - 1)]
            return [{"type": "helper_hint", "hint": hint, "hint_level": level}]
        if not ts.current_round_id:
            return [{"type": "error", "message": "진행 중인 라운드가 없습니다."}]
        round_def = episode.get_round(ts.current_round_id)
        if not round_def:
            return [{"type": "error", "message": "라운드를 찾을 수 없습니다."}]
        level = await self.state.increment_hint_level(session_id, round_def.round_id)
        hint = self.helper.get_hint(round_def, level - 1)
        return [{"type": "helper_hint", "hint": hint, "hint_level": level}]

    async def _calculate_trial_score_result(
        self, session_id: str, episode: EpisodeData, trial_id: str
    ) -> dict[str, Any]:
        ts = await self.state.get_trial_state(session_id)
        trial = episode.get_trial(trial_id)
        stage_ids = [stage.stage_id for stage in trial.stages] if trial else list(ts.stage_scores)
        trial_score = sum(ts.stage_scores.get(stage_id, 0) for stage_id in stage_ids)
        max_possible_score = sum(
            self._stage_max_possible_score(ts.difficulty, stage)
            for stage in (trial.stages if trial else [])
        )
        if not max_possible_score:
            max_possible_score = sum(ts.stage_scores.values()) or 1
        verdict = compute_final_verdict(trial_score, max_possible_score)
        ts.trial_scores[trial_id] = trial_score
        await self.state.save_trial_state(session_id, ts)
        return {
            "trial_score": trial_score,
            "stage_scores": {stage_id: ts.stage_scores.get(stage_id, 0) for stage_id in stage_ids},
            "max_possible_score": max_possible_score,
            "score_ratio": verdict["score_ratio"],
            "final_verdict": verdict["grade"],
            "verdict_label": verdict["label"],
        }

    async def _calculate_episode_score_result(
        self, session_id: str, episode: EpisodeData
    ) -> dict[str, Any]:
        ts = await self.state.get_trial_state(session_id)
        episode_score = sum(ts.trial_scores.values()) or sum(ts.stage_scores.values())
        max_possible_score = sum(
            self._stage_max_possible_score(ts.difficulty, stage)
            for trial in episode.trials
            for stage in trial.stages
        )
        if not max_possible_score:
            max_possible_score = episode_score or 1
        verdict = compute_final_verdict(episode_score, max_possible_score)
        ts.episode_total_score = episode_score
        await self.state.save_trial_state(session_id, ts)
        return {
            "trial_scores": ts.trial_scores,
            "episode_score": episode_score,
            "max_possible_score": max_possible_score,
            "score_ratio": verdict["score_ratio"],
            "final_verdict": verdict["grade"],
            "verdict_label": verdict["label"],
            "ending_label": verdict["label"],
        }

    def _stage_max_possible_score(self, difficulty: str, stage: TrialStage) -> int:
        base = 100 + (10 if difficulty == "hard" else 0)
        return max(1, int(base * stage.score_weight))

    def _ending_reaction(self, score_ratio: float) -> str:
        if score_ratio >= 0.90:
            return "완벽한 변론이었습니다. 피고인은 당신을 평생 잊지 못할 겁니다."
        if score_ratio >= 0.75:
            return "오늘 회식은 제가 쏠게요!"
        return "조금 더 노력하면 좋은 변호사가 될 수 있을 겁니다."

    def _next_round(self, episode: EpisodeData, current: TrialRound) -> Optional[TrialRound]:
        rounds = sorted(episode.trial_rounds, key=lambda r: r.order)
        for i, r in enumerate(rounds):
            if r.round_id == current.round_id and i + 1 < len(rounds):
                return rounds[i + 1]
        return None

    async def _all_core_claims_weakened(self, session_id: str, episode: EpisodeData) -> bool:
        ts = await self.state.get_trial_state(session_id)
        core = set(episode.core_claim_ids())
        weakened = set(ts.prosecution_claim_state.weakened_claim_ids)
        return core.issubset(weakened)

    async def _finish_trial(self, session_id: str, episode: EpisodeData) -> list[dict[str, Any]]:
        ts = await self.state.get_trial_state(session_id)
        max_possible_score = sum(r.scoring.max_score for r in episode.trial_rounds)
        verdict = compute_final_verdict(ts.total_score, max_possible_score)
        grade = str(verdict["grade"])
        await self.state.finish_trial(session_id, grade)
        judge = self.judge_actor.final_verdict_lines(
            verdict, ts.prosecution_claim_state.weakened_claim_ids
        )
        return [
            {
                "type": "trial_finished",
                "total_score": ts.total_score,
                "max_possible_score": max_possible_score,
                "score_ratio": verdict["score_ratio"],
                "round_scores": ts.round_scores,
                "weakened_claim_ids": ts.prosecution_claim_state.weakened_claim_ids,
                "final_verdict": grade,
                "final_verdict_label": verdict["label"],
                "judge_lines": [ln.model_dump() for ln in judge.lines],
            }
        ]

    # --- Legacy compatibility ---
    async def process_player_input(
        self,
        session_id: str,
        raw_text: Optional[str] = None,
        parsed=None,
        legacy_payload: Optional[dict] = None,
    ) -> list[dict[str, Any]]:
        meta = await self.state.get_meta(session_id)
        episode = self.get_episode(meta.episode_id)
        if episode.trial_rounds and meta.phase in (GamePhase.COURT, GamePhase.INVESTIGATION):
            text = raw_text or (legacy_payload or {}).get("text", "")
            ev_ids = []
            if legacy_payload and legacy_payload.get("evidence_id"):
                ev_ids = [legacy_payload["evidence_id"]]
            if meta.phase == GamePhase.INVESTIGATION:
                return [{"type": "error", "message": "법정을 먼저 시작하세요."}]
            return await self.process_player_answer(session_id, text, ev_ids)
        return [{"type": "error", "message": "레거시 모드 비활성화. start-court 후 player_answer를 사용하세요."}]
