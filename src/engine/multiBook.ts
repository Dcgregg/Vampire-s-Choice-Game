import { Book, PlayerState, Series } from '../types';

export function nextPlayableBook(
  series: Series,
  books: Record<string, Book>,
  currentBookId: string
): Book | null {
  const ordered = [...series.books].sort((a, b) => a.order - b.order);
  const currentIndex = ordered.findIndex((ref) => ref.id === currentBookId);
  if (currentIndex < 0 || currentIndex + 1 >= ordered.length) return null;
  const next = ordered[currentIndex + 1];
  return next.status === 'available' ? books[next.id] ?? null : null;
}

/** Move only book-local progress. Character, rewards, bonds and flags carry forward. */
export function enterNextBook(state: PlayerState, book: Book): PlayerState {
  const startingSceneId = book.startingSceneId;
  const firstChapter = book.chapters[0]?.number;
  if (!startingSceneId || firstChapter === undefined) return state;
  return {
    ...state,
    progress: {
      ...state.progress,
      currentBookId: book.id,
      currentChapter: firstChapter,
      currentSceneId: startingSceneId,
      completedChapters: [],
      sceneHistory: [...state.progress.sceneHistory, startingSceneId],
    },
  };
}
