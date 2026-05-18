const API_BASE =
  import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_BASE || 'http://localhost:8000';

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

export async function fetchEpisodes() {
  return request('/api/episodes');
}

export async function fetchEpisode(episodeId) {
  return request(`/api/episodes/${episodeId}`);
}

export async function createSession(episodeId, playerRole = 'defense', difficulty = 'easy') {
  return request('/api/sessions', {
    method: 'POST',
    body: JSON.stringify({ episode_id: episodeId, player_role: playerRole, difficulty }),
  });
}

export async function fetchSession(sessionId) {
  return request(`/api/sessions/${sessionId}`);
}

export async function collectEvidence(sessionId, objectId, evidenceId) {
  return request(`/api/sessions/${sessionId}/collect`, {
    method: 'POST',
    body: JSON.stringify({ object_id: objectId, evidence_id: evidenceId }),
  });
}

export async function startCourt(sessionId) {
  return request(`/api/sessions/${sessionId}/start-court`, { method: 'POST' });
}
