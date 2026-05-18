const ASSET_ROOT = '/court-assets';

const SPEAKER_ASSETS = {
  player: {
    label: '변호사',
    position: 'defense',
    folder: 'defense',
    expressions: {
      idle: '0.png',
      normal: '0.png',
      serious: 'serious.png',
      objection: 'serious.png',
      elaborate: 'elaborate.png',
      think: 'elaborate.png',
      success: 'elaborate.png',
    },
  },
  def_001: {
    label: '변호사',
    position: 'defense',
    folder: 'defense',
    expressions: {
      idle: '0.png',
      serious: 'serious.png',
      objection: 'serious.png',
      think: 'elaborate.png',
    },
  },
  pros_001: {
    label: '검사',
    position: 'prosecutor',
    folder: 'prosecutor',
    expressions: {
      idle: '0.png',
      normal: '0.png',
      objection: 'angry.png',
      angry: 'angry.png',
      pressure: 'angry.png',
      think: 'embarrassed.png',
      sweat: 'embarrassed.png',
      shaken: 'gasp-1.png',
      gasp: 'gasp-2.png',
      breakdown: 'gasp-3.png',
      laugh: 'laugh.png',
    },
  },
  wit_001: {
    label: '증인',
    position: 'witness',
    folder: 'witness',
    expressions: {
      idle: '0.png',
      normal: '0.png',
      sweat: 'embarrased.png',
      shake: 'embarrased.png',
      shaken: 'embarrased.png',
      angry: 'angry.png',
      gasp: 'gasp.png',
      breakdown: 'gasp.png',
      laugh: 'laugh.png',
    },
  },
  wit_002: {
    label: '증인',
    position: 'witness',
    folder: 'witness',
    expressions: {
      idle: '0.png',
      normal: '0.png',
      sweat: 'embarrased.png',
      shake: 'embarrased.png',
      shaken: 'embarrased.png',
      angry: 'angry.png',
      gasp: 'gasp.png',
      breakdown: 'gasp.png',
      laugh: 'laugh.png',
    },
  },
  judge_001: {
    label: '판사',
    position: 'judge',
    folder: 'judge',
    expressions: {
      idle: '0.png',
      normal: '0.png',
      think: 'intrigued.png',
      intrigued: 'intrigued.png',
      objection: 'intrigued.png',
      smile: 'smile.png',
      success: 'smile.png',
    },
  },
  helper: {
    label: '조력자',
    position: 'defense',
    folder: 'defense',
    expressions: {
      idle: '0.png',
      think: 'elaborate.png',
      serious: 'serious.png',
    },
  },
};

export function resolveSpeaker(speakerId) {
  if (SPEAKER_ASSETS[speakerId]) return SPEAKER_ASSETS[speakerId];
  if (speakerId?.startsWith('wit_')) return SPEAKER_ASSETS.wit_001;
  if (speakerId?.startsWith('pros')) return SPEAKER_ASSETS.pros_001;
  if (speakerId?.startsWith('judge')) return SPEAKER_ASSETS.judge_001;
  return SPEAKER_ASSETS.player;
}

export function resolveSpeakerSlot(speakerId) {
  if (speakerId === 'player' || speakerId === 'def_001' || speakerId === 'helper') return 'player';
  if (speakerId?.startsWith('wit_')) return 'wit_001';
  if (speakerId?.startsWith('pros')) return 'pros_001';
  if (speakerId?.startsWith('judge')) return 'judge_001';
  return speakerId || 'player';
}

export function resolveExpression(config, animationState = 'idle') {
  const key = (animationState || 'idle').toLowerCase();
  return config.expressions[key] || config.expressions.idle || '0.png';
}

export function getSpeakerLabel(speakerId) {
  return resolveSpeaker(speakerId).label;
}

export function getSpeakerAvatar(speakerId, animationState = 'idle') {
  const config = resolveSpeaker(speakerId);
  return `${ASSET_ROOT}/characters/${config.folder}/${resolveExpression(config, animationState)}`;
}

export function getCourtroomBackground() {
  return `${ASSET_ROOT}/backgrounds/courtroom.png`;
}
