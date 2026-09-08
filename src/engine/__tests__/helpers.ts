import { PlayerState } from '../../types';
import { INITIAL_CHARACTERS } from '../../data/characters';
import { INITIAL_ACHIEVEMENTS } from '../../data/achievements';

/** Deterministic, deep-cloned base player state for engine unit tests. */
export function baseState(overrides: Partial<PlayerState> = {}): PlayerState {
  return {
    player: {
      name: 'Elena',
      genderIdentity: 'Woman',
      sexualOrientation: 'Bisexual',
      createdAt: 0,
    },
    relationships: structuredClone(INITIAL_CHARACTERS),
    flags: {},
    progress: {
      currentBookId: 'book1',
      currentChapter: 1,
      currentSceneId: 'b1_c1_s1',
      completedChapters: [],
      sceneHistory: ['b1_c1_s1'],
    },
    bloodCoins: 100,
    dailyStreak: 3,
    lastLoginDate: '2026-01-01',
    achievements: structuredClone(INITIAL_ACHIEVEMENTS),
    settings: { fontSize: 'normal', ambientAudio: false, reducedMotion: false, highContrast: false },
    version: 2,
    ...overrides,
  };
}
