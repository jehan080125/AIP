import { useState } from 'react';
import './index.css';
import EpisodeSelect from './pages/EpisodeSelect';
import Investigation from './pages/Investigation';
import Courtroom from './pages/Courtroom';
import { createSession, startCourt } from './api/client';

const SCREENS = { SELECT: 'select', INVESTIGATION: 'investigation', COURT: 'court' };

export default function App() {
  const [screen, setScreen] = useState(SCREENS.SELECT);
  const [sessionId, setSessionId] = useState(null);
  const [episode, setEpisode] = useState(null);
  const [inventory, setInventory] = useState([]);
  const [startCourtEvents, setStartCourtEvents] = useState([]);
  const [courtRecords, setCourtRecords] = useState([]);
  const [difficulty, setDifficulty] = useState('easy');
  const [error, setError] = useState('');

  const handleStart = async (episodeId, selectedDifficulty = 'easy') => {
    setError('');
    try {
      const res = await createSession(episodeId, 'defense', selectedDifficulty);
      setSessionId(res.session_id);
      setEpisode(res.episode);
      setDifficulty(selectedDifficulty);
      setInventory([]);
      setCourtRecords([]);
      setScreen(SCREENS.INVESTIGATION);
    } catch (e) {
      setError(e.message);
    }
  };

  const handleStartCourt = async () => {
    setError('');
    try {
      const res = await startCourt(sessionId);
      setStartCourtEvents(res.events || []);
      setCourtRecords(res.court_records || []);
      setScreen(SCREENS.COURT);
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <motion-app className="w-full min-h-screen flex items-center justify-center p-4">
      {error && (
        <p className="fixed top-4 left-1/2 -translate-x-1/2 text-red-400 bg-black/80 px-4 py-2 rounded z-50 text-sm">
          {error}
        </p>
      )}

      {screen === SCREENS.SELECT && <EpisodeSelect onStart={handleStart} />}

      {screen === SCREENS.INVESTIGATION && sessionId && episode && (
        <Investigation
          sessionId={sessionId}
          episode={episode}
          inventory={inventory}
          onInventoryChange={setInventory}
          onStartCourt={handleStartCourt}
        />
      )}

      {screen === SCREENS.COURT && sessionId && (
        <Courtroom
          sessionId={sessionId}
          episode={episode}
          inventory={inventory}
          startCourtEvents={startCourtEvents}
          initialCourtRecords={courtRecords}
          difficulty={difficulty}
        />
      )}
    </motion-app>
  );
}
