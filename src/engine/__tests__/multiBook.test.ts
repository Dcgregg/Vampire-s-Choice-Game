import { describe, expect, it } from 'vitest';
import { enterNextBook, nextPlayableBook } from '../multiBook';
import { Book, PlayerState, Series } from '../../types';

const book = (id: string, start: string): Book => ({
  id, title: id, subtitle: id, synopsis: '', coverArtStyle: '',
  startingSceneId: start,
  chapters: [{ number: 1, title: '', summary: '', firstSceneId: start, totalScenes: 1, rewardCoins: 0 }],
});
const series: Series = {
  id: 'series', title: '', description: '', books: [
    { id: 'book1', order: 1, status: 'available' },
    { id: 'book2', order: 2, status: 'available' },
  ],
};

it('only exposes the immediate published sequel with loaded content', () => {
  expect(nextPlayableBook(series, { book1: book('book1', 'one'), book2: book('book2', 'two') }, 'book1')?.id)
    .toBe('book2');
  expect(nextPlayableBook({ ...series, books: [series.books[0], { ...series.books[1], status: 'coming_soon' }] },
    { book1: book('book1', 'one'), book2: book('book2', 'two') }, 'book1')).toBeNull();
});

describe('cross-book carry-over', () => {
  it('resets book-local progress while preserving character, rewards, bonds and flags', () => {
    const state = {
      player: { name: 'Elena' }, bloodCoins: 88,
      relationships: { lucian: { affinity: 72 } }, flags: { keptOath: true },
      achievements: { oath: { unlockedAt: 1 } },
      progress: { currentBookId: 'book1', currentChapter: 3, currentSceneId: 'end',
        completedChapters: [1, 2, 3], completedBooks: ['book1'], sceneHistory: ['one', 'end'] },
    } as unknown as PlayerState;
    const next = enterNextBook(state, book('book2', 'two'));
    expect(next.progress).toMatchObject({ currentBookId: 'book2', currentChapter: 1,
      currentSceneId: 'two', completedChapters: [], completedBooks: ['book1'] });
    expect(next.player).toBe(state.player);
    expect(next.relationships).toBe(state.relationships);
    expect(next.flags).toBe(state.flags);
    expect(next.achievements).toBe(state.achievements);
    expect(next.bloodCoins).toBe(88);
  });
});
