import { useEffect, useMemo, useState } from 'react';
import {
  getCourtroomBackground,
  resolveExpression,
  resolveSpeaker,
  resolveSpeakerSlot,
} from './speakerAssets';

const cutoutCache = new Map();

function deferSetState(callback) {
  window.queueMicrotask(callback);
}

function useCutoutImage(src) {
  const [processedSrc, setProcessedSrc] = useState('');

  useEffect(() => {
    let cancelled = false;

    if (!src) {
      deferSetState(() => {
        if (!cancelled) setProcessedSrc('');
      });
      return () => {
        cancelled = true;
      };
    }

    if (cutoutCache.has(src)) {
      deferSetState(() => {
        if (!cancelled) setProcessedSrc(cutoutCache.get(src));
      });
      return () => {
        cancelled = true;
      };
    }

    const image = new Image();
    image.crossOrigin = 'anonymous';
    image.decoding = 'async';

    image.onload = () => {
      try {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d', { willReadFrequently: true });
        canvas.width = image.naturalWidth;
        canvas.height = image.naturalHeight;
        ctx.drawImage(image, 0, 0);

        const { width, height } = canvas;
        const imageData = ctx.getImageData(0, 0, width, height);
        const { data } = imageData;
        const visited = new Uint8Array(width * height);
        const queue = [];

        const isNearWhite = (offset) => {
          const alpha = data[offset + 3];
          if (alpha < 12) return true;
          const r = data[offset];
          const g = data[offset + 1];
          const b = data[offset + 2];
          const max = Math.max(r, g, b);
          const min = Math.min(r, g, b);
          return r > 232 && g > 232 && b > 232 && max - min < 34;
        };

        const push = (x, y) => {
          if (x < 0 || y < 0 || x >= width || y >= height) return;
          const pixel = y * width + x;
          if (visited[pixel]) return;
          const offset = pixel * 4;
          if (!isNearWhite(offset)) return;
          visited[pixel] = 1;
          queue.push(pixel);
        };

        for (let x = 0; x < width; x += 1) {
          push(x, 0);
          push(x, height - 1);
        }
        for (let y = 0; y < height; y += 1) {
          push(0, y);
          push(width - 1, y);
        }

        for (let i = 0; i < queue.length; i += 1) {
          const pixel = queue[i];
          const offset = pixel * 4;
          data[offset + 3] = 0;
          const x = pixel % width;
          const y = Math.floor(pixel / width);
          push(x + 1, y);
          push(x - 1, y);
          push(x, y + 1);
          push(x, y - 1);
        }

        ctx.putImageData(imageData, 0, 0);
        const dataUrl = canvas.toDataURL('image/png');
        cutoutCache.set(src, dataUrl);
        if (!cancelled) setProcessedSrc(dataUrl);
      } catch {
        cutoutCache.set(src, src);
        if (!cancelled) setProcessedSrc(src);
      }
    };

    image.onerror = () => {
      if (!cancelled) setProcessedSrc(src);
    };
    image.src = src;

    return () => {
      cancelled = true;
    };
  }, [src]);

  return src ? processedSrc || src : '';
}

function DialogueBubble({ line }) {
  const config = resolveSpeaker(resolveSpeakerSlot(line.speaker));
  return (
    <div className={`vn-bubble vn-bubble--${config.position}`}>
      <strong>{config.label}</strong>
      <p>{line.text}</p>
    </div>
  );
}

export default function CharacterStage({
  activeSpeakerId = null,
  animationState = 'idle',
  currentLine = null,
  className = '',
}) {
  const activeSlot = resolveSpeakerSlot(activeSpeakerId);
  const config = useMemo(() => resolveSpeaker(activeSlot), [activeSlot]);
  const expressionFile = resolveExpression(config, animationState);
  const src = activeSpeakerId
    ? `/court-assets/characters/${config.folder}/${expressionFile}`
    : '';
  const cutoutSrc = useCutoutImage(src);
  const hasSpeaker = Boolean(activeSpeakerId && activeSpeakerId !== 'system');

  return (
    <section className={`vn-stage ${className}`}>
      <img
        className="vn-stage__background"
        src={getCourtroomBackground()}
        alt=""
        aria-hidden="true"
      />
      <div className="vn-stage__vignette" aria-hidden="true" />

      {hasSpeaker && (
        <div
          className={`vn-character vn-character--${config.position} vn-character--motion-${animationState} ${
            animationState === 'breakdown' ? 'anim-breakdown' : ''
          } ${animationState === 'sweat' || animationState === 'shake' ? 'anim-shake' : ''}`}
        >
          <img src={cutoutSrc} alt={config.label} className="vn-character__image" />
        </div>
      )}

      {currentLine?.text && <DialogueBubble key={currentLine.id} line={currentLine} />}
    </section>
  );
}
