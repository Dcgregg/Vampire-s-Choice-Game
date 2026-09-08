import { describe, it, expect } from 'vitest';
import { validateContent } from '../validate';
import { ALL_SCENES, BOOKS } from '../../data/story';
import { INITIAL_CHARACTERS } from '../../data/characters';
import { INITIAL_ACHIEVEMENTS } from '../../data/achievements';
import { Scene } from '../../types';

describe('content validation', () => {
  it('the shipped Book 1 content has no integrity errors', () => {
    const issues = validateContent({
      scenes: ALL_SCENES,
      books: BOOKS,
      achievements: INITIAL_ACHIEVEMENTS,
      characters: INITIAL_CHARACTERS,
    });
    const errors = issues.filter((i) => i.level === 'error');
    if (errors.length) console.error(errors);
    expect(errors).toHaveLength(0);
  });

  it('detects a dangling nextSceneId', () => {
    const scenes: { [id: string]: Scene } = {
      s1: {
        id: 's1', bookId: 'b', chapterNumber: 1, chapterTitle: 'c', sceneTitle: 's', sceneIndex: 1,
        paragraphs: ['x'],
        choices: [{ id: 'x', text: 't', nextSceneId: 'nowhere' }],
      },
    };
    const issues = validateContent({ scenes, books: {}, achievements: {}, characters: {} });
    expect(issues.some((i) => i.level === 'error' && i.message.includes('nowhere'))).toBe(true);
  });

  it('detects an unknown achievement reference', () => {
    const scenes: { [id: string]: Scene } = {
      s1: {
        id: 's1', bookId: 'b', chapterNumber: 1, chapterTitle: 'c', sceneTitle: 's', sceneIndex: 1,
        paragraphs: ['x'],
        choices: [{ id: 'x', text: 't', nextSceneId: 's1', effects: { achievementId: 'GHOST' } }],
      },
    };
    const issues = validateContent({ scenes, books: {}, achievements: {}, characters: {} });
    expect(issues.some((i) => i.level === 'error' && i.message.includes('GHOST'))).toBe(true);
  });
});
