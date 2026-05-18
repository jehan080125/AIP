import { useState, useEffect, useCallback, useRef } from 'react';
import { useAudio } from './useAudio';

const WS_BASE =
  import.meta.env.VITE_WS_BASE_URL || import.meta.env.VITE_WS_BASE || 'ws://localhost:8000';

export function useGameWebSocket(sessionId, initialEvents = [], initialCourtRecords = []) {
  const { playSfx, playBgm, fadeToBgm } = useAudio();
  const [isConnected, setIsConnected] = useState(false);
  const [transcript, setTranscript] = useState([]);
  const [animationState, setAnimationState] = useState('idle');
  const [activeSpeaker, setActiveSpeaker] = useState(null);
  const [trialUi, setTrialUi] = useState({
    stageId: null,
    stageType: null,
    life: 0,
    helperEnabled: true,
    witnessMentalBand: 'steady',
    judgePersuasionBand: 'low',
    currentStatement: null,
    stageCleared: null,
    stageFailed: null,
    judgeComment: null,
    witnessReaction: null,
    prosecutorPressure: null,
    witnessMental: null,
    judgePersuasion: null,
    trialScore: null,
    episodeScore: null,
    ending: null,
    roundId: null,
    roundIndex: 0,
    witness: null,
    witnessTestimony: null,
    currentClaim: null,
    prosecutorPlan: null,
    totalScore: 0,
    attemptCount: 0,
    hintLevel: 0,
    lastEvaluation: null,
    lastScoring: null,
    relatedEvidenceIds: [],
    trialFinished: null,
  });
  const [courtRecords, setCourtRecords] = useState(initialCourtRecords || []);
  const wsRef = useRef(null);
  const processedInitialEventsRef = useRef(null);
  const recentLineKeysRef = useRef(new Map());
  const speakerMotionIndexRef = useRef(new Map());

  const appendSystem = useCallback((text) => {
    setTranscript((p) => [...p, { id: Date.now() + Math.random(), speaker: 'system', text }]);
  }, []);

  const pickFallbackAnimation = useCallback((speaker, fallbackAnimation = 'idle') => {
    if (fallbackAnimation && fallbackAnimation !== 'idle') return fallbackAnimation;

    const pools = {
      pros_001: ['objection', 'angry', 'think'],
      wit_001: ['idle', 'gasp', 'angry', 'sweat'],
      wit_002: ['idle', 'gasp', 'angry', 'sweat'],
      judge_001: ['think', 'idle', 'smile'],
      player: ['serious', 'elaborate'],
      def_001: ['serious', 'elaborate'],
      helper: ['think', 'serious'],
    };
    const key = speaker?.startsWith('wit_') ? 'wit_001' : speaker;
    const pool = pools[key] || ['idle'];
    const previous = speakerMotionIndexRef.current.get(key) || 0;
    speakerMotionIndexRef.current.set(key, previous + 1);
    return pool[previous % pool.length];
  }, []);

  const appendLines = useCallback((lines, defaultSpeaker = 'system', fallbackAnimation = 'idle') => {
    const now = Date.now();
    const messages = (lines || [])
      .map((line) => {
        const speaker = line.speaker || defaultSpeaker;
        const dialogue = line.dialogue || line.text || '';
        let anim = line.animation_tag || fallbackAnimation || 'idle';
        const parsed = dialogue
          .replace(/\[anim:\s*([^\]]+)\]/g, (_, t) => {
            anim = t.trim();
            return '';
          })
          .trim();

        const key = `${speaker}:${parsed}`;
        const lastSeen = recentLineKeysRef.current.get(key);
        if (lastSeen && now - lastSeen < 1500) return null;
        recentLineKeysRef.current.set(key, now);

        if (anim === 'idle' || anim === 'normal') {
          anim = pickFallbackAnimation(speaker, fallbackAnimation);
        }

        return {
          id: Date.now() + Math.random(),
          speaker,
          text: parsed,
          animationState: anim,
        };
      })
      .filter(Boolean);

    for (const [key, seenAt] of recentLineKeysRef.current.entries()) {
      if (now - seenAt > 5000) recentLineKeysRef.current.delete(key);
    }

    if (!messages.length) return;

    const last = messages[messages.length - 1];
    setActiveSpeaker(last.speaker);
    setAnimationState(last.animationState);
    setTranscript((prev) => [...prev, ...messages]);
  }, [pickFallbackAnimation]);

  const handleServerEvent = useCallback(
    (data) => {
      if (data.sfx) playSfx(data.sfx);
      if (data.bgm) playBgm(data.bgm);
      if (data.fade_to_bgm) fadeToBgm(data.fade_to_bgm);

      if (data.type === 'error' || data.status === 'error') {
        appendSystem(`오류: ${data.message}`);
        return;
      }

      if (data.type === 'round_started') {
        setTrialUi((u) => ({
          ...u,
          roundId: data.round_id,
          roundIndex: data.round_index,
          witness: data.active_witness,
          witnessTestimony: data.fixed_witness_testimony,
          currentClaim: data.current_claim,
          relatedEvidenceIds: data.related_evidence_ids || [],
          prosecutorPlan: null,
          attemptCount: 0,
          hintLevel: 0,
        }));
      }

      if (data.type === 'stage_started') {
        setTrialUi((u) => ({
          ...u,
          stageId: data.stage_id,
          stageType: data.stage_type,
          life: data.life,
          helperEnabled: data.helper_enabled,
          witness: data.active_witness || u.witness,
          witnessMentalBand: data.witness_mental_band || u.witnessMentalBand,
          judgePersuasionBand: data.judge_persuasion_band || u.judgePersuasionBand,
          currentStatement: null,
          stageCleared: null,
          stageFailed: null,
          judgeComment: null,
          witnessReaction: null,
          prosecutorPressure: null,
          witnessMental: null,
          judgePersuasion: null,
        }));
        appendSystem(`스테이지 시작: ${data.stage_type}`);
      }

      if (data.type === 'prosecutor_plan') {
        setTrialUi((u) => ({
          ...u,
          prosecutorPlan: data,
          currentClaim: u.currentClaim || { claim_id: data.selected_claim_id },
        }));
      }

      if (data.type === 'witness_testimony' || data.type === 'witness_reaction') {
        if (data.statement_id || data.text) {
          setTrialUi((u) => ({
            ...u,
            currentStatement: { statement_id: data.statement_id, text: data.text },
            witnessTestimony: data.text
              ? { statement_id: data.statement_id, text: data.text }
              : u.witnessTestimony,
          }));
        }
        if (data.type === 'witness_reaction') {
          setTrialUi((u) => ({ ...u, witnessReaction: data }));
        }
        appendLines(data.lines, 'wit_001', data.type === 'witness_reaction' ? 'gasp' : 'idle');
      }

      if (data.type === 'witness_counter') {
        setTrialUi((u) => ({
          ...u,
          currentStatement: { statement_id: data.statement_id, text: data.text },
        }));
        appendLines(data.lines, 'wit_001', 'angry');
      }

      if (data.type === 'witness_shaken' || data.type === 'witness_breakdown') {
        setTrialUi((u) => ({
          ...u,
          witnessMentalBand: data.witness_mental_band || u.witnessMentalBand,
          witnessReaction: data,
        }));
        appendLines(data.lines, 'wit_001', data.type === 'witness_breakdown' ? 'gasp' : 'sweat');
      }

      if (data.type === 'witness_mental_update') {
        setTrialUi((u) => ({
          ...u,
          witnessMentalBand: data.witness_mental_band || u.witnessMentalBand,
          witnessMental: data.remaining_witness_mental,
        }));
      }

      if (data.type === 'prosecutor_response' || data.type === 'prosecutor_pressure') {
        setTrialUi((u) => ({ ...u, prosecutorPressure: data }));
        const modeFallback =
          data.type === 'prosecutor_pressure'
            ? 'angry'
            : data.mode === 'retreat'
              ? 'think'
              : data.mode === 'pivot'
                ? 'objection'
                : 'objection';
        appendLines(data.lines, 'pros_001', modeFallback);
      }

      if (data.type === 'judge_comment' || data.type === 'trial_finished') {
        if (data.type === 'judge_comment') {
          setTrialUi((u) => ({ ...u, judgeComment: data }));
        }
        if (data.judge_lines) appendLines(data.judge_lines, 'judge_001', 'think');
        if (data.lines) appendLines(data.lines, 'judge_001', 'think');
      }

      if (data.type === 'answer_evaluated') {
        setTrialUi((u) => ({
          ...u,
          lastEvaluation: data.evaluation,
          lastScoring: data.scoring,
          totalScore: data.scoring?.total_score_after ?? u.totalScore,
        }));
        appendSystem(data.scoring?.feedback || data.evaluation?.reason || '평가 완료');
      }

      if (data.type === 'defense_argument_evaluated') {
        setTrialUi((u) => ({ ...u, lastEvaluation: data.evaluation }));
        appendSystem(data.evaluation?.reason || `평가: ${data.evaluation?.verdict || '완료'}`);
      }

      if (data.type === 'life_update') {
        setTrialUi((u) => ({ ...u, life: data.remaining_life }));
        appendSystem(`생명 감소: -${data.life_loss}`);
      }

      if (data.type === 'judge_persuasion_update') {
        setTrialUi((u) => ({
          ...u,
          judgePersuasionBand: data.judge_persuasion_band || u.judgePersuasionBand,
          judgePersuasion: data.judge_persuasion,
        }));
      }

      if (data.type === 'usable_statement_added') {
        setCourtRecords((prev) => {
          const record = data.record;
          if (!record || prev.some((r) => r.statement_id === record.statement_id)) return prev;
          return [...prev, record];
        });
      }

      if (data.type === 'stage_cleared') {
        setTrialUi((u) => ({ ...u, stageCleared: data, stageFailed: null }));
        appendSystem(`스테이지 클리어 +${data.stage_score}점`);
      }

      if (data.type === 'stage_failed') {
        setTrialUi((u) => ({ ...u, stageFailed: data, stageCleared: null }));
        appendSystem('패배. 스테이지를 다시 시작하세요.');
      }

      if (data.type === 'trial_score') {
        setTrialUi((u) => ({ ...u, trialScore: data }));
      }

      if (data.type === 'episode_score') {
        setTrialUi((u) => ({ ...u, episodeScore: data }));
      }

      if (data.type === 'ending') {
        setTrialUi((u) => ({ ...u, ending: data }));
        if (data.judge_lines) appendLines(data.judge_lines, 'judge_001', 'success');
        appendLines(data.lines, 'helper');
      }

      if (data.type === 'helper_hint') {
        setTrialUi((u) => ({ ...u, hintLevel: data.hint_level }));
        appendSystem(`[힌트] ${data.hint}`);
      }

      if (data.type === 'claim_weakened') {
        appendSystem(`검사 주장 약화: ${data.claim_id}`);
      }

      if (data.type === 'round_cleared') {
        appendSystem(`라운드 클리어 +${data.score}점`);
      }

      if (data.type === 'trial_finished') {
        setTrialUi((u) => ({
          ...u,
          trialFinished: data,
          totalScore: data.total_score,
        }));
      }

      if (data.type === 'actor_lines') {
        appendLines(data.lines || []);
      }
    },
    [appendLines, appendSystem, fadeToBgm, playBgm, playSfx]
  );

  useEffect(() => {
    if (!initialEvents.length) return;
    const initialEventsKey = sessionId || 'pending-session';
    if (processedInitialEventsRef.current === initialEventsKey) return;
    processedInitialEventsRef.current = initialEventsKey;
    initialEvents.forEach(handleServerEvent);
  }, [initialEvents, handleServerEvent, sessionId]);

  useEffect(() => {
    if (!sessionId) return undefined;

    const ws = new WebSocket(`${WS_BASE}/ws/trial/${sessionId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      setTranscript((p) =>
        p.length ? p : [{ id: 'sys1', speaker: 'system', text: '법정에 입장했습니다.' }]
      );
    };

    ws.onclose = () => setIsConnected(false);
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      handleServerEvent(data);
    };

    return () => {
      ws.close();
    };
  }, [sessionId, handleServerEvent]);

  const sendPlayerAnswer = useCallback(
    (text, selectedEvidenceIds, stageId = null) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
      const evLabel = selectedEvidenceIds.length ? `[증거: ${selectedEvidenceIds.join(', ')}] ` : '';
      setActiveSpeaker('player');
      setAnimationState('serious');
      setTranscript((p) => [
        ...p,
        {
          id: Date.now(),
          speaker: 'player',
          text: evLabel + text,
          animationState: 'serious',
        },
      ]);
      setTrialUi((u) => ({ ...u, attemptCount: u.attemptCount + 1 }));
      wsRef.current.send(
        JSON.stringify({
          type: stageId ? 'defense_argument' : 'player_answer',
          session_id: sessionId,
          stage_id: stageId,
          text,
          selected_evidence_ids: selectedEvidenceIds,
        })
      );
    },
    [sessionId]
  );

  const requestHint = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: 'request_hint', session_id: sessionId }));
  }, [sessionId]);

  const restartStage = useCallback(
    (stageId) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN || !stageId) return;
      wsRef.current.send(JSON.stringify({ type: 'restart_stage', session_id: sessionId, stage_id: stageId }));
    },
    [sessionId]
  );

  const summonWitness = useCallback(
    (stageId) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN || !stageId) return;
      wsRef.current.send(JSON.stringify({ type: 'summon_witness', session_id: sessionId, stage_id: stageId }));
    },
    [sessionId]
  );

  return {
    isConnected,
    transcript,
    animationState,
    activeSpeaker,
    trialUi,
    courtRecords,
    sendPlayerAnswer,
    requestHint,
    restartStage,
    summonWitness,
    handleServerEvent,
  };
}
