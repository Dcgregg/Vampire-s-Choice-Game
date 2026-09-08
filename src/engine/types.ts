/**
 * Story Engine — shared engine types.
 *
 * The engine is a pure, framework-agnostic layer. It never imports React,
 * the state singleton, audio, or persistence. It operates on PlayerState and
 * returns new PlayerState plus a list of EngineEvents describing what happened,
 * which the host (GameStateManager) translates into UI side-effects.
 */
import { Achievement, PlayerState, Scene } from '../types';

export type EngineEvent =
  | { type: 'achievementUnlocked'; achievementId: string; achievement: Achievement }
  | { type: 'consequence'; message: string }
  | { type: 'coinsChanged'; delta: number; total: number }
  | { type: 'relationshipChanged'; characterId: string; delta: number; newAffinity: number }
  | { type: 'chapterCompleted'; chapter: number }
  | { type: 'streakChanged'; value: number };

/** Resolves a scene id to a Scene, or null when it does not exist. */
export type SceneLookup = (sceneId: string) => Scene | null;

export interface SelectChoiceResult {
  /** false when the choice's conditions are not satisfied (not executable). */
  ok: boolean;
  reason?: 'conditions_not_met';
  /** Resulting player state (unchanged when ok === false). */
  state: PlayerState;
  events: EngineEvent[];
  /** true when the choice ends the flow and the host should return to landing. */
  returnToLanding: boolean;
  /** Set when navigation targeted a scene id that could not be resolved. */
  sceneNotFound?: string;
}
