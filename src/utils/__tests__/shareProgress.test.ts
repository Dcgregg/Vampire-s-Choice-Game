import { describe, expect, it } from 'vitest';
import type { PlayerState } from '../../types';
import { buildProgressShareText } from '../shareProgress';

const playerState = (overrides: Partial<PlayerState> = {}) => ({
  player: { name: 'Secret Character', genderIdentity: 'private identity', sexualOrientation: 'private preference' },
  progress: { currentChapter: 3, sceneHistory: ['start', 'hall'], completedBooks: [] },
  bloodCoins: 900,
  humanity: 42,
  ...overrides,
} as PlayerState);

describe('buildProgressShareText', () => {
  it('shares chapter and exploration progress without character or account stats', () => {
    const text = buildProgressShareText(playerState(), 'https://example.test');
    expect(text).toContain('Chapter 3');
    expect(text).toContain('2 scenes');
    expect(text).toContain('https://example.test');
    expect(text).not.toContain('Secret Character');
    expect(text).not.toContain('private identity');
    expect(text).not.toContain('private preference');
    expect(text).not.toContain('900');
    expect(text).not.toContain('42');
  });

  it('uses completed-book progress when available', () => {
    const text = buildProgressShareText(playerState({ progress: { currentChapter: 1, sceneHistory: [], completedBooks: ['book1', 'book2'] } as PlayerState['progress'] }), 'https://example.test');
    expect(text).toContain('completed 2 books');
    expect(text).not.toContain('0 scenes');
  });
});
