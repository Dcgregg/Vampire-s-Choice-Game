/**
 * Story Engine — Orchestrator.
 *
 * The single entry point for making a choice. It composes the three concerns:
 *
 *   Player selects choice
 *     → evaluate conditions   (conditions.ts)   — is it executable?
 *     → apply effects         (effects.ts)      — mutate a copy of player state
 *     → determine next scene  (navigation.ts)   — advance story progress
 *     → return new state       (host persists it)
 *
 * A choice whose conditions are not satisfied is NOT executable: the original
 * state is returned untouched with ok === false.
 */
import { PlayerState, SceneChoice } from '../types';
import { evaluateCondition } from './conditions';
import { applyEffects } from './effects';
import { navigate } from './navigation';
import { SceneLookup, SelectChoiceResult } from './types';

export function selectChoice(
  state: PlayerState,
  choice: SceneChoice,
  getScene: SceneLookup
): SelectChoiceResult {
  // 1. Validate conditions — locked choices cannot be executed.
  const condition = evaluateCondition(choice.condition, state);
  if (!condition.available) {
    return { ok: false, reason: 'conditions_not_met', state, events: [] };
  }

  // 2. Apply effects to a copy of the state.
  const { state: afterEffects, events: effectEvents } = applyEffects(state, choice.effects);

  // 3. Determine the next scene / progression.
  const nav = navigate(afterEffects, choice, getScene);

  const nextState: PlayerState = { ...afterEffects, progress: nav.progress };

  return {
    ok: true,
    state: nextState,
    events: [...effectEvents, ...nav.events],
    bookCompleted: nav.bookCompleted,
    sceneNotFound: nav.sceneNotFound,
  };
}
