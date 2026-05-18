import { useEffect, useState } from 'react';
import { fetchEpisodes } from '../api/client';

export default function EpisodeSelect({ onStart }) {
  const [episodes, setEpisodes] = useState([]);
  const [difficulty, setDifficulty] = useState('easy');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchEpisodes()
      .then((data) => setEpisodes(data.episodes || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-[var(--text-muted)]">로딩 중...</p>;
  if (error) return <p className="text-red-400">{error}</p>;

  return (
    <motion-select className="glass-panel p-8 max-w-lg w-full flex flex-col gap-6">
      <h1 className="text-2xl font-bold">⚖️ AI Attorney</h1>
      <p className="text-[var(--text-muted)]">
        당신은 <strong>변호인</strong>입니다. 검사의 주장과 증인 증언의 모순을 찾아 피고인을 변호하세요.
      </p>
      <motion-episode-list className="flex flex-col gap-2">
        {episodes.map((ep) => (
          <div key={ep.episode_id} className="p-4 rounded-xl border border-[var(--border-color)]">
            <span className="font-semibold">{ep.title}</span>
            <span className="block text-xs text-[var(--text-muted)]">{ep.episode_id}</span>
            <div className="mt-3 flex gap-2">
              {(ep.difficulty_available || ['easy', 'hard']).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setDifficulty(mode)}
                  className={`px-3 py-1 rounded border text-xs ${
                    difficulty === mode ? 'border-yellow-400 bg-yellow-500/20' : 'border-[var(--border-color)]'
                  }`}
                >
                  {mode}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={() => onStart(ep.episode_id, difficulty)}
              className="mt-3 w-full bg-[var(--accent)] px-4 py-2 rounded-lg text-sm font-bold"
            >
              시작
            </button>
          </div>
        ))}
      </motion-episode-list>
    </motion-select>
  );
}
