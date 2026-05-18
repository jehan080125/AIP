import { useCallback, useRef } from 'react';

export function useAudio() {
  const lastCueRef = useRef({ name: '', at: 0 });
  const currentBgmRef = useRef('');

  const playSfx = useCallback((name) => {
    if (!name) return;
    const now = Date.now();
    if (lastCueRef.current.name === name && now - lastCueRef.current.at < 180) return;
    lastCueRef.current = { name, at: now };
    if (import.meta.env.DEV) console.debug(`[audio:sfx] ${name}`);
  }, []);

  const playBgm = useCallback((name) => {
    if (!name || currentBgmRef.current === name) return;
    currentBgmRef.current = name;
    if (import.meta.env.DEV) console.debug(`[audio:bgm] ${name}`);
  }, []);

  const fadeToBgm = useCallback((name) => {
    if (!name || currentBgmRef.current === name) return;
    currentBgmRef.current = name;
    if (import.meta.env.DEV) console.debug(`[audio:bgm:fade] ${name}`);
  }, []);

  return { playSfx, playBgm, fadeToBgm };
}
