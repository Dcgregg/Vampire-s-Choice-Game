import { describe, it, expect } from 'vitest';
import { navigate, isCurrentBookCompleted, isBookCompleted } from '../navigation';
import { getSceneById } from '../../data/story';
import { SceneChoice } from '../../types';
import { baseState } from './helpers';

describe('navigation', () => {
  it('advances to the target scene and records history', () => {
    const state = baseState();
    const choice: SceneChoice = { id: 'c', text: 't', nextSceneId: 'b1_c1_s2a' };
    const res = navigate(state, choice, getSceneById);
    expect(res.bookCompleted).toBeUndefined();
    expect(res.progress.currentSceneId).toBe('b1_c1_s2a');
    expect(res.progress.currentChapter).toBe(1);
    expect(res.progress.sceneHistory).toContain('b1_c1_s2a');
  });

  it('does not duplicate scenes already in history', () => {
    const state = baseState({
      progress: {
        currentBookId: 'book1',
        currentChapter: 1,
        currentSceneId: 'b1_c1_s1',
        completedChapters: [],
        completedBooks: [],
        sceneHistory: ['b1_c1_s1', 'b1_c1_s2a'],
      },
    });
    const res = navigate(state, { id: 'c', text: 't', nextSceneId: 'b1_c1_s2a' }, getSceneById);
    expect(res.progress.sceneHistory.filter((s) => s === 'b1_c1_s2a')).toHaveLength(1);
  });

  it('marks the previous chapter completed when crossing into a new chapter', () => {
    const state = baseState({
      progress: {
        currentBookId: 'book1',
        currentChapter: 1,
        currentSceneId: 'b1_c1_s4',
        completedChapters: [],
        completedBooks: [],
        sceneHistory: ['b1_c1_s4'],
      },
    });
    const res = navigate(state, { id: 'c', text: 't', nextSceneId: 'b1_c2_s1' }, getSceneById);
    expect(res.progress.currentChapter).toBe(2);
    expect(res.progress.completedChapters).toContain(1);
    expect(res.events).toContainEqual({ type: 'chapterCompleted', chapter: 1 });
  });

  it('endsBook records explicit book completion without leaving the finale scene', () => {
    const state = baseState({
      progress: {
        currentBookId: 'book1',
        currentChapter: 3,
        currentSceneId: 'b1_c3_s3',
        completedChapters: [1, 2],
        completedBooks: [],
        sceneHistory: ['b1_c3_s3'],
      },
    });
    const res = navigate(state, { id: 'end', text: 't', nextSceneId: 'b1_c3_s3', endsBook: true }, getSceneById);
    expect(res.bookCompleted).toBe('book1');
    expect(res.progress.completedBooks).toContain('book1');
    expect(res.progress.currentSceneId).toBe('b1_c3_s3'); // unchanged
    expect(res.events).toContainEqual({ type: 'bookCompleted', bookId: 'book1' });
  });

  it('reports a dangling nextSceneId without changing progress', () => {
    const state = baseState();
    const res = navigate(state, { id: 'c', text: 't', nextSceneId: 'does_not_exist' }, getSceneById);
    expect(res.sceneNotFound).toBe('does_not_exist');
    expect(res.progress).toBe(state.progress);
  });
});

describe('book completion helpers', () => {
  it('detect whether the current / a given book is complete', () => {
    const reading = baseState();
    expect(isCurrentBookCompleted(reading)).toBe(false);
    const done = baseState({
      progress: { ...reading.progress, completedBooks: ['book1'] },
    });
    expect(isCurrentBookCompleted(done)).toBe(true);
    expect(isBookCompleted(done, 'book1')).toBe(true);
    expect(isBookCompleted(done, 'book2')).toBe(false);
  });
});
