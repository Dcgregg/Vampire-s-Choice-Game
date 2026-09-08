/**
 * Story Engine — Conditions.
 *
 * Determines whether content or a choice is AVAILABLE, given the player state.
 * Conditions are declarative (see ChoiceCondition). All present fields must be
 * satisfied simultaneously (logical AND). A missing/undefined condition is
 * always available. Missing referenced data (e.g. an unknown character or a
 * required flag that was never set) fails SAFE — the condition is treated as
 * unmet so unavailable content is never accidentally exposed.
 */
import {
  ChoiceCondition,
  GenderIdentity,
  PlayerState,
  SceneChoice,
  SexualOrientation,
} from '../types';

export interface ConditionResult {
  available: boolean;
  /** Human-readable reasons a condition failed (useful for tests/debugging). */
  reasons: string[];
}

function inList<T>(value: T | T[], candidate: T | undefined): boolean {
  if (candidate === undefined) return false;
  return Array.isArray(value) ? value.includes(candidate) : value === candidate;
}

export function evaluateCondition(
  condition: ChoiceCondition | undefined,
  state: PlayerState
): ConditionResult {
  if (!condition) return { available: true, reasons: [] };

  const reasons: string[] = [];

  // --- Flags ---
  if (condition.requiredFlags) {
    for (const [key, expected] of Object.entries(condition.requiredFlags)) {
      if (state.flags[key] !== expected) {
        reasons.push(`flag "${key}" !== ${String(expected)}`);
      }
    }
  }

  // --- Relationship (legacy single threshold) ---
  if (condition.minRelationship) {
    const { characterId, minValue } = condition.minRelationship;
    const char = state.relationships[characterId];
    if (!char) reasons.push(`relationship "${characterId}" is unknown`);
    else if (char.affinity < minValue) {
      reasons.push(`relationship "${characterId}" affinity ${char.affinity} < ${minValue}`);
    }
  }

  // --- Relationship (multiple thresholds) ---
  if (condition.relationships) {
    for (const r of condition.relationships) {
      const char = state.relationships[r.characterId];
      if (!char) {
        reasons.push(`relationship "${r.characterId}" is unknown`);
        continue;
      }
      if (r.min !== undefined && char.affinity < r.min) {
        reasons.push(`relationship "${r.characterId}" affinity ${char.affinity} < ${r.min}`);
      }
      if (r.max !== undefined && char.affinity > r.max) {
        reasons.push(`relationship "${r.characterId}" affinity ${char.affinity} > ${r.max}`);
      }
    }
  }

  // --- Currency / numeric variables ---
  if (condition.minCoins !== undefined && state.bloodCoins < condition.minCoins) {
    reasons.push(`bloodCoins ${state.bloodCoins} < ${condition.minCoins}`);
  }
  if (condition.maxCoins !== undefined && state.bloodCoins > condition.maxCoins) {
    reasons.push(`bloodCoins ${state.bloodCoins} > ${condition.maxCoins}`);
  }

  // --- Story progress ---
  if (condition.requiredBook !== undefined && state.progress.currentBookId !== condition.requiredBook) {
    reasons.push(`book "${state.progress.currentBookId}" !== "${condition.requiredBook}"`);
  }
  if (condition.requiredChapter !== undefined && state.progress.currentChapter < condition.requiredChapter) {
    reasons.push(`chapter ${state.progress.currentChapter} < ${condition.requiredChapter}`);
  }
  if (condition.visitedScene !== undefined && !state.progress.sceneHistory.includes(condition.visitedScene)) {
    reasons.push(`scene "${condition.visitedScene}" not visited`);
  }

  // --- Player identity / character properties ---
  if (condition.playerGender !== undefined) {
    const g = state.player?.genderIdentity as GenderIdentity | undefined;
    if (!inList(condition.playerGender, g)) reasons.push(`gender "${g ?? 'none'}" not allowed`);
  }
  if (condition.playerOrientation !== undefined) {
    const o = state.player?.sexualOrientation as SexualOrientation | undefined;
    if (!inList(condition.playerOrientation, o)) reasons.push(`orientation "${o ?? 'none'}" not allowed`);
  }

  return { available: reasons.length === 0, reasons };
}

/** Convenience: is a choice selectable given the current state? */
export function isChoiceAvailable(choice: SceneChoice, state: PlayerState): boolean {
  return evaluateCondition(choice.condition, state).available;
}

/**
 * Paragraph-level condition used by conditionParagraphs. A paragraph block is
 * visible when its flag matches expectedValue (or is simply truthy when no
 * expectedValue is given).
 */
export function isParagraphVisible(
  cond: { conditionFlag: string; expectedValue?: boolean | string | number },
  state: PlayerState
): boolean {
  const flagValue = state.flags[cond.conditionFlag];
  return cond.expectedValue !== undefined
    ? flagValue === cond.expectedValue
    : Boolean(flagValue);
}
