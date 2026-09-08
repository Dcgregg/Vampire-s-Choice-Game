/**
 * Story Engine — Navigation.
 *
 * Determines the NEXT scene after a choice and keeps story progress consistent
 * (currentSceneId, currentChapter, sceneHistory, completedChapters). Navigation
 * is pure: it returns a new PlayerProgress plus events; it does not mutate.
 *
 * Chapter completion: when a choice moves the player from a scene in chapter N
 * to a scene in a different chapter, chapter N is recorded as completed.
 */
import { PlayerProgress, PlayerState, SceneChoice } from '../types';
import { EngineEvent, SceneLookup } from './types';

export interface NavigationResult {
  progress: PlayerProgress;
  returnToLanding: boolean;
  sceneNotFound?: string;
  events: EngineEvent[];
}

export function navigate(
  state: PlayerState,
  choice: SceneChoice,
  getScene: SceneLookup
): NavigationResult {
  // Book-ending / terminal choice: do not navigate, signal a return to landing.
  if (choice.returnToLanding) {
    return { progress: state.progress, returnToLanding: true, events: [] };
  }

  const target = getScene(choice.nextSceneId);
  if (!target) {
    // Fail-safe: leave progress untouched and report the dangling id.
    return {
      progress: state.progress,
      returnToLanding: false,
      sceneNotFound: choice.nextSceneId,
      events: [],
    };
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

  return { progress, returnToLanding: false, events };
}
