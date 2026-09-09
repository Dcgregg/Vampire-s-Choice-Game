import { PlayerState, Character, PlayerProgress } from '../types';
import { INITIAL_CHARACTERS } from '../data/characters';
import { INITIAL_ACHIEVEMENTS } from '../data/achievements';
import { BOOK_VERSIONS } from '../data/story';

const STORAGE_KEY = 'vampires_choice_player_state_v1';

/**
 * Player-SAVE schema version. This is intentionally SEPARATE from content
 * versioning (CONTENT_SCHEMA_VERSION and per-book `version` in content/schema.ts).
 *
 *   v1 → initial prototype save.
 *   v2 → character/save merge + settings/progress normalisation.
 *   v3 → explicit book completion (progress.completedBooks) + contentVersions
 *        (records which authored book version a save was created/played against,
 *        enabling future content migrations to detect stale saves per book).
 */
const SAVE_SCHEMA_VERSION = 3;

/**
 * Merge saved character data with the current INITIAL_CHARACTERS base.
 * Static authored fields always come from the current base so content updates
 * reach existing players; dynamic per-player fields (affinity, status,
 * loreUnlocked) are preserved from the save.
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
    completedBooks: [],
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
  version: SAVE_SCHEMA_VERSION,
  contentVersions: { ...BOOK_VERSIONS },
};

/**
 * Pure migration + defaults merge. Given a parsed (possibly older) save object,
 * return a valid current-schema PlayerState. Safe for v1/v2/v3 inputs.
 *
 * v2 → v3 specifics:
 *   - progress.completedBooks is introduced. Existing players who had reached
 *     the Book 1 finale (flags.completedBook1 === true) are marked complete so
 *     they are NOT dropped back into an "unfinished finale" after upgrading.
 *   - contentVersions is stamped from the current bundle (pre-v3 saves cannot
 *     know their original authored version, so we assume current).
 */
export function migrateAndMerge(parsed: Partial<PlayerState>): PlayerState {
  const prevProgress = (parsed.progress || {}) as Partial<PlayerProgress>;
  const flags = (parsed.flags as PlayerState['flags']) || {};

  const completedBooks = Array.isArray(prevProgress.completedBooks)
    ? prevProgress.completedBooks
    : flags.completedBook1 === true
    ? ['book1']
    : [];

  const progress: PlayerProgress = {
    ...DEFAULT_PLAYER_STATE.progress,
    ...prevProgress,
    completedBooks,
  };

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
    progress,
    flags,
    contentVersions: {
      ...BOOK_VERSIONS,
      ...(parsed.contentVersions || {}),
    },
    version: SAVE_SCHEMA_VERSION,
  };
}

export function loadSavedState(): PlayerState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PLAYER_STATE;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return DEFAULT_PLAYER_STATE;
    return migrateAndMerge(parsed);
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
