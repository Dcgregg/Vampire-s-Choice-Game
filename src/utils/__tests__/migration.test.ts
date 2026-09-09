import { describe, it, expect } from 'vitest';
import { migrateAndMerge } from '../storage';
import { isCurrentBookCompleted } from '../../engine';
import { PlayerState } from '../../types';

/** A representative v2 save (no completedBooks / contentVersions fields). */
function v2Save(partial: Partial<PlayerState> = {}): any {
  return {
    player: { name: 'Elena', genderIdentity: 'Woman', sexualOrientation: 'Bisexual', createdAt: 1 },
    relationships: {},
    flags: {},
    progress: {
      currentBookId: 'book1',
      currentChapter: 3,
      currentSceneId: 'b1_c3_s3',
      completedChapters: [1, 2],
      sceneHistory: ['b1_c1_s1', 'b1_c3_s3'],
    },
    bloodCoins: 570,
    dailyStreak: 4,
    lastLoginDate: '2026-01-01',
    achievements: {},
    settings: { fontSize: 'normal', ambientAudio: false, reducedMotion: false, highContrast: false },
    version: 2,
    ...partial,
  };
}

describe('save migration v2 → v3', () => {
  it('adds completedBooks and stamps version 3 + contentVersions', () => {
    const migrated = migrateAndMerge(v2Save());
    expect(migrated.version).toBe(3);
    expect(Array.isArray(migrated.progress.completedBooks)).toBe(true);
    expect(migrated.contentVersions?.book1).toBe(1);
  });

  it('marks a finished v2 player (flags.completedBook1) as having completed book1', () => {
    const save = v2Save();
    save.flags.completedBook1 = true;
    const migrated = migrateAndMerge(save);
    expect(migrated.progress.completedBooks).toContain('book1');
    // The key guarantee: a completed book must not resume as an unfinished finale.
    expect(isCurrentBookCompleted(migrated)).toBe(true);
  });

  it('does not mark book1 complete for an in-progress v2 save', () => {
    const save = v2Save();
    save.progress.currentSceneId = 'b1_c2_s1';
    save.progress.currentChapter = 2;
    const migrated = migrateAndMerge(save);
    expect(migrated.progress.completedBooks).toEqual([]);
    expect(isCurrentBookCompleted(migrated)).toBe(false);
  });

  it('preserves an already-present completedBooks array (v3 save)', () => {
    const save = v2Save();
    save.version = 3;
    save.progress.completedBooks = ['book1'];
    const migrated = migrateAndMerge(save);
    expect(migrated.progress.completedBooks).toEqual(['book1']);
  });

  it('does not lose core progress during migration', () => {
    const migrated = migrateAndMerge(v2Save());
    expect(migrated.bloodCoins).toBe(570);
    expect(migrated.progress.currentSceneId).toBe('b1_c3_s3');
    expect(migrated.progress.completedChapters).toEqual([1, 2]);
    expect(migrated.player?.name).toBe('Elena');
  });
});
