import { useCallback, useEffect, useMemo, useState } from 'react';
import { useGameWebSocket } from '../hooks/useGameWebSocket';
import CharacterStage from '../components/CharacterStage';
import { getSpeakerAvatar, getSpeakerLabel } from '../components/speakerAssets';

const EVIDENCE_IMAGES = {
  ev_001: '/court-assets/evidence/im3.png',
  ev_002: '/court-assets/evidence/im2.png',
  ev_003: '/court-assets/evidence/im1.png',
};

const EVIDENCE_LABELS = {
  ev_001: '부검 감정서',
  ev_002: '현장 CCTV 기록',
  ev_003: '가로등 정비 기록',
  ev_004: '피해자 통화 기록',
  ev_005: '지문 감정서',
};

const EVIDENCE_SUMMARIES = {
  ev_001: '사망 시각과 사인을 정리한 공식 서류.',
  ev_002: '사건 현장 주변 CCTV 기록.',
  ev_003: '사건 시각 공원 중앙 가로등의 정비 기록.',
  ev_004: '피해자가 사건 전 통화한 기록.',
  ev_005: '현장에서 채취된 지문 감정 결과.',
};

const PEOPLE = [
  { id: 'pros_001', label: '검사', role: '검찰 측 주장', aliases: ['pros_001'] },
  { id: 'player', label: '변호사', role: '변호인', aliases: ['player', 'def_001', 'helper'] },
  { id: 'wit_001', label: '증인', role: '증언자', aliases: ['wit_001', 'wit_002'] },
  { id: 'judge_001', label: '판사', role: '재판 진행', aliases: ['judge_001'] },
];

function isEditableTarget(target) {
  return ['INPUT', 'TEXTAREA', 'SELECT'].includes(target?.tagName);
}

function matchesSpeaker(speaker, person) {
  return person.aliases.includes(speaker) || (person.id === 'wit_001' && speaker?.startsWith('wit_'));
}

function readEvidenceName(item) {
  return EVIDENCE_LABELS[item.id] || item.name || item.id;
}

export default function Courtroom({
  sessionId,
  episode,
  inventory: initialInventory = [],
  startCourtEvents = [],
  initialCourtRecords = [],
}) {
  const {
    isConnected,
    transcript,
    trialUi,
    courtRecords,
    sendPlayerAnswer,
    requestHint,
    restartStage,
    summonWitness,
  } = useGameWebSocket(sessionId, startCourtEvents, initialCourtRecords);

  const [inputText, setInputText] = useState('');
  const [selectedEvidenceIds, setSelectedEvidenceIds] = useState([]);
  const [notice, setNotice] = useState('');
  const [isRecordOpen, setIsRecordOpen] = useState(false);
  const [recordTab, setRecordTab] = useState('evidence');
  const [detailItem, setDetailItem] = useState(null);
  const inventory = initialInventory;

  const evidenceList = useMemo(
    () =>
      (episode?.evidences || [])
        .filter((e) => inventory.includes(e.id))
        .map((item) => ({
          ...item,
          name: readEvidenceName(item),
          description: EVIDENCE_SUMMARIES[item.id] || item.description,
          imageSrc: EVIDENCE_IMAGES[item.id] || null,
        })),
    [episode, inventory]
  );

  const selectableRecords = useMemo(
    () =>
      (courtRecords || [])
        .filter((record) => record.usable_as_evidence)
        .map((record) => ({
          id: record.statement_id,
          name: `${getSpeakerLabel(record.speaker)}의 증언`,
          description: record.text,
          fact: record.source,
          speaker: record.speaker,
          imageSrc: getSpeakerAvatar(record.speaker, 'idle'),
        })),
    [courtRecords]
  );

  const spokenTranscript = useMemo(
    () => transcript.filter((msg) => msg.speaker !== 'system' && msg.text),
    [transcript]
  );
  const lastSpokenLine = spokenTranscript.at(-1) || null;
  const [dismissedLineId, setDismissedLineId] = useState(null);
  useEffect(() => {
    if (!lastSpokenLine) return undefined;
    const timer = window.setTimeout(() => {
      setDismissedLineId(lastSpokenLine.id);
    }, 5200);
    return () => window.clearTimeout(timer);
  }, [lastSpokenLine]);
  const visibleLine = lastSpokenLine?.id === dismissedLineId ? null : lastSpokenLine;
  const stageSpeaker = visibleLine?.speaker || null;

  const peopleWithLines = useMemo(
    () =>
      PEOPLE.map((person) => ({
        ...person,
        spokenLines: transcript.filter((msg) => msg.speaker !== 'system' && matchesSpeaker(msg.speaker, person)),
        records: (courtRecords || []).filter((record) => matchesSpeaker(record.speaker, person)),
      })),
    [transcript, courtRecords]
  );

  const selectedItems = useMemo(() => {
    const allItems = [...evidenceList, ...selectableRecords];
    return selectedEvidenceIds.map((id) => allItems.find((item) => item.id === id)).filter(Boolean);
  }, [evidenceList, selectableRecords, selectedEvidenceIds]);

  const currentTrial = useMemo(
    () => episode?.trials?.find((trial) => trial.stages?.some((stage) => stage.stage_id === trialUi.stageId)),
    [episode, trialUi.stageId]
  );

  const currentStage = useMemo(
    () => currentTrial?.stages?.find((stage) => stage.stage_id === trialUi.stageId) || null,
    [currentTrial, trialUi.stageId]
  );

  const canSummonDefenseWitness =
    trialUi.stageType === 'vs_prosecutor' && currentStage?.summon_witness_action;

  const toggleEvidence = useCallback((item) => {
    const id = typeof item === 'string' ? item : item.id;
    if (!id) return;
    setDetailItem(typeof item === 'string' ? null : item);
    setSelectedEvidenceIds((prev) => {
      if (prev.includes(id)) {
        setNotice('');
        return prev.filter((x) => x !== id);
      }
      if (prev.length >= 2) {
        setNotice('증거는 최대 2개까지 선택할 수 있습니다.');
        return prev;
      }
      setNotice('');
      return [...prev, id];
    });
  }, []);

  const handleSend = useCallback(() => {
    const text = inputText.trim();
    if (!text) return;
    if (text.length > 100) {
      setNotice('주장은 100자 이내로 입력해야 합니다.');
      return;
    }
    sendPlayerAnswer(text, selectedEvidenceIds, trialUi.stageId);
    setInputText('');
    setSelectedEvidenceIds([]);
    setNotice('');
  }, [inputText, selectedEvidenceIds, sendPlayerAnswer, trialUi.stageId]);

  useEffect(() => {
    const onKeyDown = (event) => {
      if (isEditableTarget(event.target)) {
        if (event.key === 'Escape') setIsRecordOpen(false);
        return;
      }
      if (event.key.toLowerCase() === 'e') {
        event.preventDefault();
        setIsRecordOpen((value) => !value);
      }
      if (event.key.toLowerCase() === 'h' && trialUi.helperEnabled) requestHint();
      if (event.key === 'Escape') setIsRecordOpen(false);
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [requestHint, trialUi.helperEnabled]);

  const lifeMarks = Array.from({ length: trialUi.life || 0 }, (_, index) => (
    <span key={index} className="life-dot" />
  ));

  if (trialUi.trialFinished || trialUi.ending) {
    const final = trialUi.trialFinished || trialUi.ending;
    return (
      <main className="courtroom-screen">
        <CharacterStage className="courtroom-visual" />
        <section className="verdict-panel">
          <h1>최종 판결</h1>
          <strong>{final.final_verdict}</strong>
          <p>
            총점 {final.total_score ?? final.episode_score}/
            {final.max_possible_score ?? '-'}
          </p>
          <p>{final.final_verdict_label}</p>
        </section>
      </main>
    );
  }

  return (
    <main className="courtroom-screen">
      <CharacterStage
        activeSpeakerId={stageSpeaker}
        animationState={visibleLine?.animationState || 'idle'}
        currentLine={visibleLine}
        className="courtroom-visual"
      />

      <header className="court-hud court-hud--top">
        <div>
          <strong>{episode?.title || 'AI Attorney'}</strong>
        </div>
        <div className="court-hud__right">
          <div className="life-strip" aria-label={`남은 생명 ${trialUi.life || 0}`}>
            {lifeMarks}
          </div>
          <span className={isConnected ? 'status-dot status-dot--on' : 'status-dot'} />
          <button type="button" className="record-key" onClick={() => setIsRecordOpen(true)}>
            E
          </button>
        </div>
      </header>

      {notice && <p className="court-notice">{notice}</p>}

      <form
        className="court-composer"
        onSubmit={(event) => {
          event.preventDefault();
          handleSend();
        }}
      >
        {selectedItems.length > 0 && (
          <div className="composer-evidence-row">
            {selectedItems.map((item) => (
              <button
                key={item.id}
                type="button"
                className="selected-chip"
                onClick={() => toggleEvidence(item.id)}
              >
                {item.name}
              </button>
            ))}
          </div>
        )}

        <div className="composer-input-shell">
          <textarea
            value={inputText}
            onChange={(event) => setInputText(event.target.value.slice(0, 100))}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                handleSend();
              }
            }}
            maxLength={100}
            rows={1}
            placeholder="반박할 내용을 입력하세요"
            className="composer-textarea"
          />
          <span className={inputText.length >= 90 ? 'composer-count composer-count--warn' : 'composer-count'}>
            {inputText.length}/100
          </span>
          <button
            type="submit"
            disabled={!isConnected || !inputText.trim()}
            className="composer-send"
          >
            전송
          </button>
        </div>
        <div className="composer-actions">
          {trialUi.helperEnabled && (
            <button type="button" onClick={requestHint}>
              힌트
            </button>
          )}
          {canSummonDefenseWitness && (
            <button type="button" onClick={() => summonWitness(trialUi.stageId)}>
              {currentStage.summon_witness_action?.label || '증인 소환'}
            </button>
          )}
          {trialUi.stageFailed && (
            <button type="button" onClick={() => restartStage(trialUi.stageId)}>
              재시작
            </button>
          )}
        </div>
      </form>

      {isRecordOpen && (
        <div className="record-backdrop" onMouseDown={() => setIsRecordOpen(false)}>
          <aside className="record-panel" onMouseDown={(event) => event.stopPropagation()}>
            <header className="record-panel__header">
              <div>
                <span>Court Record</span>
                <strong>증거와 증언</strong>
              </div>
              <button type="button" onClick={() => setIsRecordOpen(false)}>
                닫기
              </button>
            </header>

            <nav className="record-tabs" aria-label="Court Record tabs">
              {[
                ['evidence', '증거 파일'],
                ['people', '인물 파일'],
                ['statements', '발언 기록'],
              ].map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  className={recordTab === id ? 'record-tab record-tab--active' : 'record-tab'}
                  onClick={() => setRecordTab(id)}
                >
                  {label}
                </button>
              ))}
            </nav>

            {recordTab === 'evidence' && (
            <section className="record-section">
              <h2>증거물</h2>
              <div className="evidence-grid">
                {evidenceList.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={
                      selectedEvidenceIds.includes(item.id)
                        ? 'evidence-card evidence-card--selected'
                        : 'evidence-card'
                    }
                    onClick={() => toggleEvidence(item)}
                  >
                    {item.imageSrc ? (
                      <img src={item.imageSrc} alt="" />
                    ) : (
                      <span className="evidence-card__placeholder">{item.id}</span>
                    )}
                    <strong>{item.name}</strong>
                    <small>{item.description}</small>
                  </button>
                ))}
                {evidenceList.length === 0 && <p className="empty-copy">수집한 증거가 없습니다.</p>}
              </div>
            </section>
            )}

            {recordTab === 'people' && (
            <section className="record-section">
              <h2>인물</h2>
              <div className="people-list">
                {peopleWithLines.map((person) => (
                  <details key={person.id} className="person-row">
                    <summary>
                      <img src={getSpeakerAvatar(person.id, 'idle')} alt="" />
                      <span>
                        <strong>{person.label}</strong>
                        <small>{person.role}</small>
                      </span>
                    </summary>
                    <div className="person-row__body">
                      {person.records.length > 0 && (
                        <div className="person-statements">
                          <b>증거로 쓸 수 있는 증언</b>
                          {person.records.map((record) => (
                            <button
                              key={record.statement_id}
                              type="button"
                              className={
                                selectedEvidenceIds.includes(record.statement_id)
                                  ? 'statement-pill statement-pill--selected'
                                  : 'statement-pill'
                              }
                              onClick={() =>
                                toggleEvidence({
                                  id: record.statement_id,
                                  name: `${person.label}의 증언`,
                                  description: record.text,
                                  fact: record.source,
                                })
                              }
                            >
                              {record.text}
                            </button>
                          ))}
                        </div>
                      )}
                      <div className="person-statements">
                        <b>발언 기록</b>
                        {person.spokenLines.length > 0 ? (
                          person.spokenLines.map((line) => <p key={line.id}>{line.text}</p>)
                        ) : (
                          <p>아직 발언이 없습니다.</p>
                        )}
                      </div>
                    </div>
                  </details>
                ))}
              </div>
            </section>
            )}

            {recordTab === 'statements' && (
              <section className="record-section">
                <h2>발언 기록</h2>
                <div className="people-list">
                  {(courtRecords || []).map((record) => (
                    <button
                      key={record.statement_id}
                      type="button"
                      className={
                        selectedEvidenceIds.includes(record.statement_id)
                          ? 'statement-pill statement-pill--selected'
                          : 'statement-pill'
                      }
                      disabled={!record.usable_as_evidence}
                      onClick={() =>
                        record.usable_as_evidence &&
                        toggleEvidence({
                          id: record.statement_id,
                          name: `${getSpeakerLabel(record.speaker)}의 발언`,
                          description: record.text,
                          fact: record.source,
                        })
                      }
                    >
                      <strong>{getSpeakerLabel(record.speaker)}</strong>
                      <span>{record.text}</span>
                    </button>
                  ))}
                  {(courtRecords || []).length === 0 && <p className="empty-copy">아직 발언 기록이 없습니다.</p>}
                </div>
              </section>
            )}

            {detailItem && (
              <section className="record-detail">
                <strong>{detailItem.name}</strong>
                <p>{detailItem.description}</p>
                {detailItem.fact && <small>{detailItem.fact}</small>}
              </section>
            )}

            <footer className="record-panel__footer">
              {trialUi.helperEnabled && (
                <button type="button" onClick={requestHint}>
                  힌트
                </button>
              )}
              {trialUi.stageFailed && (
                <button type="button" onClick={() => restartStage(trialUi.stageId)}>
                  재시작
                </button>
              )}
            </footer>
          </aside>
        </div>
      )}
    </main>
  );
}
