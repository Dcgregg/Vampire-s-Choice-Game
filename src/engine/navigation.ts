/**
 * Story Engine — Navigation & progression.
 *
 * Determines the NEXT scene after a choice and keeps story progress consistent
 * (currentSceneId, currentChapter, sceneHistory, completedChapters,
 * completedBooks). Navigation is pure: it returns a new PlayerProgress plus
 * events; it does not mutate.
 *
 * Chapter completion: when a choice moves the player from a scene in chapter N
 * to a scene in a different chapter, chapter N is recorded as completed.
 *
 * Book completion: a choice flagged `endsBook` records the current book in
 * completedBooks (explicit state, not inferred from being on the finale scene)
 * and signals the host; it does not navigate away from the finale scene.
 */
import { PlayerProgress, PlayerState, SceneChoice } from '../types';
import { EngineEvent, SceneLookup } from './types';

export interface NavigationResult {
  progress: PlayerProgress;
  bookCompleted?: string;
  sceneNotFound?: string;
  events: EngineEvent[];
}

/** Is the player's current book already marked complete? */
export function isCurrentBookCompleted(state: PlayerState): boolean {
  return state.progress.completedBooks.includes(state.progress.currentBookId);
}

export function isBookCompleted(state: PlayerState, bookId: string): boolean {
  return state.progress.completedBooks.includes(bookId);
}

export function navigate(
  state: PlayerState,
  choice: SceneChoice,
  getScene: SceneLookup
): NavigationResult {
  // Book-ending choice: record explicit completion; stay on the finale scene.
  if (choice.endsBook) {
    const bookId = state.progress.currentBookId;
    const completedBooks = state.progress.completedBooks.includes(bookId)
      ? state.progress.completedBooks
      : [...state.progress.completedBooks, bookId];
    return {
      progress: { ...state.progress, completedBooks },
      bookCompleted: bookId,
      events: [{ type: 'bookCompleted', bookId }],
    };
  }

  const target = getScene(choice.nextSceneId);
  if (!target) {
    // Fail-safe: leave progress untouched and report the dangling id.
    return { progress: state.progress, sceneNotFound: choice.nextSceneId, events: [] };
  }

  const fromScene = getScene(state.progress.currentSceneId);
  const events: EngineEvent[] = [];

  const completedChapters = [...state.progress.completedChapters];
  if (
    fromScene &&
    target.chapterNumber !== fromScene.chapterNumber &&
    !completedChapters.includes(fromScene.chapterNumber)
  ) {
    completedChapters.push(fromScene.chapterNumber);
    events.push({ type: 'chapterCompleted', chapter: fromScene.chapterNumber });
  }

  const sceneHistory = state.progress.sceneHistory.includes(target.id)
    ? state.progress.sceneHistory
    : [...state.progress.sceneHistory, target.id];

  const progress: PlayerProgress = {
    ...state.progress,
    currentSceneId: target.id,
    currentChapter: target.chapterNumber,
    completedChapters,
    sceneHistory,
  };

  return { progress, events };
}
