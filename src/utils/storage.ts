import { PlayerState, Character } from '../types';
import { INITIAL_CHARACTERS } from '../data/characters';
import { INITIAL_ACHIEVEMENTS } from '../data/achievements';

const STORAGE_KEY = 'vampires_choice_player_state_v1';
const CURRENT_VERSION = 2;

/**
 * Merge saved character data with the current INITIAL_CHARACTERS base.
 * Static authored fields (name, title, description, avatar, romanceEligible)
 * always come from the current base so content updates reach existing players.
 * Dynamic per-player fields (affinity, status, loreUnlocked) are preserved
 * from the save when present. This closes the character/save migration gap.
 */
function mergeCharacters(saved: unknown): { [id: string]: Character } {
  const out: { [id: string]: Character } = {};
  const savedMap = (saved && typeof saved === 'object' ? saved : {}) as {
    [id: string]: Partial<Character>;
  };
  for (const [id, base] of Object.entries(INITIAL_CHARACTERS)) {
    const s = savedMap[id];
    out[id] = s
      ? {
          ...base,
          affinity: typeof s.affinity === 'number' ? s.affinity : base.affinity,
          status: s.status ?? base.status,
          loreUnlocked: Array.isArray(s.loreUnlocked) ? s.loreUnlocked : base.loreUnlocked,
        }
      : base;
  }
  return out;
}

export const DEFAULT_PLAYER_STATE: PlayerState = {
  player: null,
  relationships: INITIAL_CHARACTERS,
  flags: {},
  progress: {
    currentBookId: 'book1',
    currentChapter: 1,
    currentSceneId: 'b1_c1_s1',
    completedChapters: [],
    sceneHistory: ['b1_c1_s1'],
  },
  bloodCoins: 250,
  dailyStreak: 3,
  lastLoginDate: new Date().toISOString().split('T')[0],
  achievements: INITIAL_ACHIEVEMENTS,
  settings: {
    fontSize: 'normal',
    ambientAudio: false,
    reducedMotion: false,
    highContrast: false,
  },
  version: CURRENT_VERSION,
};

export function loadSavedState(): PlayerState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return DEFAULT_PLAYER_STATE;
    }
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') {
      return DEFAULT_PLAYER_STATE;
    }

    // Merge with defaults to ensure schema robustness if fields are missing
    return {
      ...DEFAULT_PLAYER_STATE,
      ...parsed,
      relationships: mergeCharacters(parsed.relationships),
      achievements: {
        ...INITIAL_ACHIEVEMENTS,
        ...(parsed.achievements || {}),
      },
      settings: {
        ...DEFAULT_PLAYER_STATE.settings,
        ...(parsed.settings || {}),
      },
      progress: {
        ...DEFAULT_PLAYER_STATE.progress,
        ...(parsed.progress || {}),
      },
      flags: parsed.flags || {},
      version: CURRENT_VERSION,
    };
  } catch (err) {
    console.error('Failed to parse saved state from localStorage:', err);
    return DEFAULT_PLAYER_STATE;
  }
}

export function savePlayerState(state: PlayerState): boolean {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    return true;
  } catch (err) {
    console.error('Failed to save player state to localStorage:', err);
    return false;
  }
}

export function clearPlayerState(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (err) {
    console.error('Failed to clear player state:', err);
  }
}
