from typing import Any

from backend.ai_services.answer_evaluator import AnswerEvaluatorLLM
from backend.core.state_manager import StateManager
from backend.schemas.court import CourtRecord, TruthStatus
from backend.schemas.episode import EpisodeData, StageType, TrialStage
from backend.schemas.trial import AnswerVerdict, DefenseArgumentEvaluation, RelevanceLevel, StageResult


class StageEngine:
    def __init__(self, state: StateManager, evaluator: AnswerEvaluatorLLM):
        self.state = state
        self.evaluator = evaluator

    async def process_defense_argument(
        self,
        session_id: str,
        episode: EpisodeData,
        stage: TrialStage,
        text: str,
        selected_evidence_ids: list[str],
    ) -> list[dict[str, Any]]:
        if len(selected_evidence_ids) > 2:
            return [{"type": "error", "message": "증거는 최대 2개까지 선택할 수 있습니다."}]
        if len(text) > 100:
            return [{"type": "error", "message": "주장은 100자 이내로 입력해야 합니다."}]

        if stage.stage_type == StageType.VS_WITNESS:
            return await self._process_vs_witness(
                session_id, episode, stage, text, selected_evidence_ids
            )
        return await self._process_vs_prosecutor(
            session_id, episode, stage, text, selected_evidence_ids
        )

    async def _process_vs_witness(
        self,
        session_id: str,
        episode: EpisodeData,
        stage: TrialStage,
        text: str,
        selected_evidence_ids: list[str],
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        ts = await self.state.get_trial_state(session_id)
        current_statement = self._current_witness_statement(stage, ts.current_testimony_id, ts.current_counter_statement_id)
        if current_statement is None:
            return [{"type": "error", "message": "현재 공격할 증언을 찾을 수 없습니다."}]

        await self.state.append_dialogue(session_id, "player", text)
        selected_details = await self._selected_evidence_details(session_id, episode, selected_evidence_ids)
        court_records = [record.model_dump() for record in await self.state.get_court_records(session_id)]
        evaluation = await self.evaluator.evaluate_stage_argument(
            stage_type=stage.stage_type.value,
            current_stage=stage,
            current_statement=current_statement,
            user_text=text,
            selected_evidence_ids=selected_evidence_ids,
            selected_evidence_details=selected_details,
            court_records=court_records,
        )
        await self._increment_stage_attempt(session_id, stage.stage_id)
        events.append(
            {
                "type": "defense_argument_evaluated",
                "stage_id": stage.stage_id,
                "evaluation": evaluation.model_dump(),
                "failure_type": self._classify_failure(text, selected_evidence_ids, evaluation)
                if evaluation.verdict in (AnswerVerdict.FAIL, AnswerVerdict.IRRELEVANT)
                else None,
                "current_statement_id": current_statement.statement_id,
                "current_statement": current_statement.model_dump(),
                "selected_evidence_ids": selected_evidence_ids,
                "selected_evidence_details": selected_details,
            }
        )

        if evaluation.verdict in (AnswerVerdict.SUCCESS, AnswerVerdict.PARTIAL_SUCCESS):
            damage = current_statement.damage_on_success
            if evaluation.verdict == AnswerVerdict.PARTIAL_SUCCESS:
                damage = max(10, damage // 2)
            mental = await self.state.apply_witness_mental_damage(
                session_id, stage.stage_id, damage
            )
            events.append(
                {
                    "type": "witness_mental_update",
                    "stage_id": stage.stage_id,
                    "witness_id": stage.active_witness_id,
                    "remaining_witness_mental": mental,
                    "witness_mental_band": self._mental_band(mental),
                    "mental_damage": damage,
                    "expression_state": self._witness_expression(mental),
                    "animation_tag": self._witness_expression(mental),
                    "camera_effect": "flash" if evaluation.verdict == AnswerVerdict.SUCCESS else None,
                    "crowd_reaction": "murmur" if mental <= 65 else None,
                }
            )

            if mental <= (stage.clear_condition.witness_mental_lte or 0):
                result = await self._clear_stage(session_id, stage)
                events.append(
                    {
                        "type": "stage_cleared",
                        **result.model_dump(),
                        "sfx": "sfx_gavel_3",
                        "animation_tag": "success",
                        "camera_effect": "flash",
                        "crowd_reaction": "murmur",
                    }
                )
                return events

            counter_id = getattr(current_statement, "counter_statement_id", None) or getattr(
                current_statement, "next_counter_statement_id", None
            )
            if evaluation.verdict == AnswerVerdict.SUCCESS and counter_id:
                counter = stage.counter_by_id(counter_id)
                if counter:
                    await self._add_statement_record(
                        session_id,
                        stage,
                        counter.statement_id,
                        counter.text,
                        "witness_counter",
                        usable=True,
                    )
                    await self.state.set_current_statement(
                        session_id, testimony_id=None, counter_statement_id=counter.statement_id
                    )
                    events.append(
                        {
                            "type": "usable_statement_added",
                            "record": {
                                "statement_id": counter.statement_id,
                                "speaker": stage.active_witness_id,
                                "text": counter.text,
                                "source": "witness_counter",
                                "usable_as_evidence": True,
                                "stage_id": stage.stage_id,
                            },
                        }
                    )
                    events.append(
                        {
                            "type": "witness_counter",
                            "stage_id": stage.stage_id,
                            "statement_id": counter.statement_id,
                            "text": counter.text,
                            "next_counter_statement": counter.model_dump(),
                            "witness_id": stage.active_witness_id,
                        }
                    )
                    events.append({"type": "court_record_updated"})
            return events

        life_loss = getattr(current_statement, "life_loss_on_fail", 1)
        life = await self.state.apply_life_loss(session_id, life_loss)
        events.append(
            {
                "type": "life_update",
                "stage_id": stage.stage_id,
                "remaining_life": life,
                "life_loss": life_loss,
                "animation": "shake",
                "animation_tag": "shake",
                "camera_effect": "shake",
                "crowd_reaction": "murmur",
            }
        )
        if life <= 0:
            await self.state.fail_stage(session_id, stage.stage_id)
            result = StageResult(
                stage_id=stage.stage_id,
                cleared=False,
                failed=True,
                remaining_life=0,
                stage_score=0,
                max_possible_score=self._stage_max_possible_score(
                    await self.state.get_trial_state(session_id), stage
                ),
                score_ratio=0.0,
                feedback="생명이 모두 소진되었습니다. 스테이지를 재시작하십시오.",
            )
            events.append(
                {
                    "type": "stage_failed",
                    **result.model_dump(),
                    "sfx": "sfx_gavel_3",
                    "animation_tag": "breakdown",
                    "camera_effect": "shake",
                    "crowd_reaction": "murmur",
                }
            )
        return events

    async def _process_vs_prosecutor(
        self,
        session_id: str,
        episode: EpisodeData,
        stage: TrialStage,
        text: str,
        selected_evidence_ids: list[str],
    ) -> list[dict[str, Any]]:
        ts = await self.state.get_trial_state(session_id)
        await self.state.append_dialogue(session_id, "player", text)
        await self._increment_stage_attempt(session_id, stage.stage_id)
        if stage.requires_defense_witness and not ts.defense_witness_summoned_by_stage.get(stage.stage_id):
            life = await self.state.apply_life_loss(session_id, 1)
            events = [
                {
                    "type": "defense_argument_evaluated",
                    "stage_id": stage.stage_id,
                    "evaluation": DefenseArgumentEvaluation(
                        relevance="partially_relevant",
                        core_match_score=0.3,
                        logic_score=0.3,
                        evidence_usage_score=0.3,
                        verdict="fail",
                        reason="이 검사 논리는 변호인측 증인 소환 없이는 아직 뒤집을 수 없습니다.",
                    ).model_dump(),
                    "failure_type": "missing_defense_witness",
                },
                {
                    "type": "life_update",
                    "stage_id": stage.stage_id,
                    "remaining_life": life,
                    "life_loss": 1,
                    "camera_effect": "shake",
                },
            ]
            if life <= 0:
                await self.state.fail_stage(session_id, stage.stage_id)
                result = StageResult(
                    stage_id=stage.stage_id,
                    cleared=False,
                    failed=True,
                    remaining_life=0,
                    stage_score=0,
                    max_possible_score=self._stage_max_possible_score(
                        await self.state.get_trial_state(session_id), stage
                    ),
                    score_ratio=0.0,
                    feedback="생명이 모두 소진되었습니다. 스테이지를 재시작하십시오.",
                )
                events.append({"type": "stage_failed", **result.model_dump(), "sfx": "sfx_gavel_3"})
            return events

        persuasion = await self.state.apply_judge_persuasion(session_id, stage.stage_id, 35)
        events = [
            {
                "type": "defense_argument_evaluated",
                "stage_id": stage.stage_id,
                "evaluation": DefenseArgumentEvaluation(
                    relevance="relevant",
                    core_match_score=0.65,
                    logic_score=0.65,
                    evidence_usage_score=0.6 if selected_evidence_ids else 0.35,
                    verdict="partial_success",
                    reason="변호인측 증언과 기록을 통해 검사의 단정을 일부 흔들었습니다.",
                ).model_dump(),
                "failure_type": None,
                "selected_evidence_ids": selected_evidence_ids,
            },
            {
                "type": "judge_persuasion_update",
                "stage_id": stage.stage_id,
                "judge_persuasion": persuasion,
                "judge_persuasion_band": "high" if persuasion >= 70 else "medium",
            }
        ]
        if persuasion >= stage.judge_persuasion_threshold:
            result = await self._clear_stage(session_id, stage)
            events.append(
                {
                    "type": "stage_cleared",
                    **result.model_dump(),
                    "sfx": "sfx_gavel_3",
                    "animation_tag": "success",
                    "camera_effect": "flash",
                }
            )
        return events

    async def _clear_stage(self, session_id: str, stage: TrialStage) -> StageResult:
        score = await self._calculate_stage_score(session_id, stage)
        await self.state.clear_stage(session_id, stage.stage_id, score)
        ts = await self.state.get_trial_state(session_id)
        max_possible_score = self._stage_max_possible_score(ts, stage)
        return StageResult(
            stage_id=stage.stage_id,
            cleared=True,
            failed=False,
            remaining_life=ts.stage_life,
            stage_score=score,
            max_possible_score=max_possible_score,
            score_ratio=round(score / max_possible_score, 4) if max_possible_score else 0.0,
            feedback="스테이지 클리어!",
        )

    async def _calculate_stage_score(self, session_id: str, stage: TrialStage) -> int:
        ts = await self.state.get_trial_state(session_id)
        attempts = max(0, ts.stage_attempts.get(stage.stage_id, 1) - 1)
        life_lost = ts.life_lost_by_stage.get(stage.stage_id, 0)
        hints = ts.stage_hint_levels.get(stage.stage_id, 0)
        base = 100 - attempts * 8 - life_lost * 10 - hints * 5
        if ts.difficulty == "hard":
            base += 10
        max_possible = self._stage_max_possible_score(ts, stage)
        return min(max_possible, max(0, int(base * stage.score_weight)))

    def _stage_max_possible_score(self, ts, stage: TrialStage) -> int:
        base = 100 + (10 if ts.difficulty == "hard" else 0)
        return max(1, int(base * stage.score_weight))

    async def _increment_stage_attempt(self, session_id: str, stage_id: str) -> int:
        ts = await self.state.get_trial_state(session_id)
        ts.stage_attempts[stage_id] = ts.stage_attempts.get(stage_id, 0) + 1
        await self.state.save_trial_state(session_id, ts)
        return ts.stage_attempts[stage_id]

    async def _selected_evidence_details(
        self, session_id: str, episode: EpisodeData, selected_evidence_ids: list[str]
    ) -> list[dict[str, Any]]:
        records = {record.statement_id: record for record in await self.state.get_court_records(session_id)}
        details = []
        for evidence_id in selected_evidence_ids[:2]:
            evidence = episode.get_evidence(evidence_id)
            if evidence:
                details.append(evidence.model_dump())
            elif evidence_id in records:
                record = records[evidence_id]
                details.append(
                    {
                        "id": record.statement_id,
                        "name": f"발언 기록: {record.speaker}",
                        "description": record.text,
                        "source": record.source,
                    }
                )
        return details

    def _current_witness_statement(self, stage: TrialStage, testimony_id: str | None, counter_id: str | None):
        if counter_id:
            return stage.counter_by_id(counter_id)
        if testimony_id:
            return stage.testimony_by_id(testimony_id)
        return stage.fixed_testimony_chain[0] if stage.fixed_testimony_chain else None

    async def _add_statement_record(
        self,
        session_id: str,
        stage: TrialStage,
        statement_id: str,
        text: str,
        source: str,
        usable: bool,
    ) -> None:
        await self.state.add_court_record(
            session_id,
            CourtRecord(
                statement_id=statement_id,
                speaker=stage.active_witness_id or "witness",
                text=text,
                truth_status=TruthStatus.UNVERIFIED,
                source=source,
                usable_as_evidence=usable,
                stage_id=stage.stage_id,
            ),
        )
        if usable:
            await self.state.mark_statement_usable_as_evidence(session_id, statement_id)

    def _mental_band(self, mental: int) -> str:
        if mental <= 0:
            return "breakdown"
        if mental <= 30:
            return "critical"
        if mental <= 65:
            return "shaken"
        return "steady"

    def _witness_expression(self, mental: int) -> str:
        if mental <= 0:
            return "breakdown"
        if mental <= 30:
            return "angry"
        return "sweat"

    def _classify_failure(
        self,
        text: str,
        selected_evidence_ids: list[str],
        evaluation: DefenseArgumentEvaluation,
    ) -> str:
        stripped = text.strip()
        if evaluation.relevance == RelevanceLevel.IRRELEVANT:
            return "irrelevant_answer"
        if not selected_evidence_ids:
            return "no_evidence_selected"
        if len(stripped) < 8:
            return "too_vague"
        if evaluation.evidence_usage_score < 0.25:
            return "irrelevant_evidence"
        if evaluation.logic_score < 0.3:
            return "weak_logic"
        if evaluation.missing_points:
            return "missing_core_point"
        if evaluation.logic_score < 0.45:
            return "contradiction_not_explained"
        return "pure_speculation"
