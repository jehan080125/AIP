import { useMemo, useState } from 'react';
import { collectEvidence } from '../api/client';

export default function Investigation({ sessionId, episode, inventory, onInventoryChange, onStartCourt }) {
  const [collected, setCollected] = useState(() => new Set(inventory || []));
  const [message, setMessage] = useState('');

  const objects = episode?.clickable_objects || [];
  const evidenceMap = useMemo(() => {
    const m = {};
    (episode?.evidences || []).forEach((e) => {
      m[e.id] = e;
    });
    return m;
  }, [episode]);

  const handleClick = async (obj) => {
    if (collected.has(obj.evidence_id)) {
      setMessage('이미 수집한 증거입니다.');
      return;
    }

    setCollected((prev) => new Set(prev).add(obj.evidence_id));
    setMessage(`${obj.label}에서 증거를 발견했습니다!`);

    try {
      const res = await collectEvidence(sessionId, obj.id, obj.evidence_id);
      onInventoryChange(res.inventory || []);
    } catch (e) {
      setMessage(`서버 저장 실패: ${e.message}`);
    }
  };

  return (
    <motion-investigation className="glass-panel p-6 max-w-4xl w-full flex flex-col gap-4 h-[90vh]">
      <header className="flex justify-between items-center border-b border-[var(--border-color)] pb-3">
        <h1 className="text-xl font-bold">🔍 현장 수색 — {episode?.title}</h1>
        <button
          type="button"
          onClick={onStartCourt}
          className="bg-[var(--accent)] px-4 py-2 rounded-lg font-bold text-sm"
        >
          법정 시작 →
        </button>
      </header>

      <p className="text-sm text-[var(--text-muted)]">
        빛나는 오브젝트를 클릭해 증거를 수집하세요. (클릭 가능 여부는 서버에 매번 묻지 않습니다)
      </p>

      <motion-scene
        className="relative flex-1 bg-black/30 border border-[var(--border-color)] rounded-xl overflow-hidden"
        style={{ minHeight: 320 }}
      >
        <motion-scene-bg
          className="absolute inset-0 bg-gradient-to-br from-slate-900 to-slate-800"
          aria-label="수색 현장 배경"
        />
        {objects.map((obj) => {
          const ev = evidenceMap[obj.evidence_id];
          const done = collected.has(obj.evidence_id);
          return (
            <button
              key={obj.id}
              type="button"
              onClick={() => handleClick(obj)}
              className={`absolute transform -translate-x-1/2 -translate-y-1/2 px-3 py-2 rounded-lg text-sm border transition-all
                ${done ? 'opacity-50 border-green-500/50 bg-green-500/10' : 'border-yellow-400/60 bg-yellow-500/10 hover:scale-105 animate-pulse'}
              `}
              style={{ left: `${obj.position?.x ?? 50}%`, top: `${obj.position?.y ?? 50}%` }}
              title={ev?.name || obj.label}
            >
              {done ? '✓ ' : '◆ '}
              {obj.label}
            </button>
          );
        })}
      </motion-scene>

      {message && <p className="text-sm text-yellow-300">{message}</p>}

      <motion-inventory className="border-t border-[var(--border-color)] pt-3">
        <span className="text-sm font-semibold text-[var(--text-muted)]">수집한 증거: </span>
        <div className="flex flex-wrap gap-2 mt-2">
          {[...collected].map((id) => (
            <span key={id} className="px-3 py-1 text-xs rounded-full bg-white/10 border border-[var(--border-color)]">
              {evidenceMap[id]?.name || id}
            </span>
          ))}
          {collected.size === 0 && (
            <span className="text-xs text-[var(--text-muted)]">아직 없음</span>
          )}
        </div>
      </motion-inventory>
    </motion-investigation>
  );
}
