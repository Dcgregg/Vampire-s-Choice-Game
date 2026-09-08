/**
 * Story Engine — Effects.
 *
 * Centralised, pure state-mutation logic. This is the ONLY place player state
 * is changed in response to a choice, so reward/mutation logic is never
 * duplicated. Every function returns a NEW PlayerState (inputs are not mutated)
 * plus the EngineEvents that occurred.
 *
 * Preserved effects: relationship changes, flags, blood coins, achievements,
 * daily-streak increment, and consequence notifications.
 */
import { Achievement, ChoiceEffect, Character, PlayerState } from '../types';
import { EngineEvent } from './types';

const AFFINITY_MIN = 0;
const AFFINITY_MAX = 100;
/** Unlocking this achievement is derived from crossing an affinity threshold. */
const DANGEROUS_LIAISON_AT = 70;

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export type RelationshipStatus = Character['status'];

export function updateRelationshipStatus(affinity: number): RelationshipStatus {
  if (affinity <= 25) return 'Rival';
  if (affinity < 50) return 'Acquaintance';
  if (affinity < 65) return 'Intrigued';
  if (affinity < 85) return 'Trusted';
  return 'Devoted';
}

/** Pure achievement unlock. Idempotent: unlocking an already-unlocked id is a no-op. */
export function unlockAchievement(
  state: PlayerState,
  achievementId: string
): { state: PlayerState; event?: Extract<EngineEvent, { type: 'achievementUnlocked' }> } {
  const existing = state.achievements[achievementId];
  if (!existing || existing.unlockedAt) return { state };
  const updated: Achievement = { ...existing, unlockedAt: Date.now() };
  return {
    state: { ...state, achievements: { ...state.achievements, [achievementId]: updated } },
    event: { type: 'achievementUnlocked', achievementId, achievement: updated },
  };
}

export interface EffectResult {
  state: PlayerState;
  events: EngineEvent[];
}

/**
 * Apply a choice's effects to the player state. Order:
 *   relationships → flags → coins → streak → explicit achievement → notification.
 * Derived achievement unlocks (e.g. Dangerous Liaison) are evaluated as part of
 * the relationship step.
 */
export function applyEffects(state: PlayerState, effects?: ChoiceEffect): EffectResult {
  if (!effects) return { state, events: [] };

  let next = state;
  const events: EngineEvent[] = [];

  const tryUnlock = (id: string) => {
    const res = unlockAchievement(next, id);
    if (res.event) {
      next = res.state;
      events.push(res.event);
    }
  };

  // --- Relationships ---
  if (effects.relationshipChanges) {
    const relationships = { ...next.relationships };
    for (const [charId, delta] of Object.entries(effects.relationshipChanges)) {
      const char = relationships[charId];
      if (!char) continue; // fail-safe: ignore unknown characters
      const newAffinity = clamp(char.affinity + delta, AFFINITY_MIN, AFFINITY_MAX);
      relationships[charId] = {
        ...char,
        affinity: newAffinity,
        status: updateRelationshipStatus(newAffinity),
      };
      events.push({ type: 'relationshipChanged', characterId: charId, delta, newAffinity });
    }
    next = { ...next, relationships };
    // Derived achievement: any relationship crossing the intensity threshold.
    if (Object.values(next.relationships).some((c) => c.affinity >= DANGEROUS_LIAISON_AT)) {
      tryUnlock('DANGEROUS_LIAISON');
    }
  }

  // --- Flags ---
  if (effects.setFlags) {
    next = { ...next, flags: { ...next.flags, ...effects.setFlags } };
  }

  // --- Currency ---
  if (effects.coinsChange) {
    const total = Math.max(0, next.bloodCoins + effects.coinsChange);
    next = { ...next, bloodCoins: total };
    events.push({ type: 'coinsChanged', delta: effects.coinsChange, total });
  }

  // --- Daily streak increment (explicit, content-driven) ---
  if (effects.streakIncrement) {
    const value = next.dailyStreak + 1;
    next = { ...next, dailyStreak: value };
    events.push({ type: 'streakChanged', value });
  }

  // --- Explicit achievement ---
  if (effects.achievementId) {
    tryUnlock(effects.achievementId);
  }

  // --- Consequence notification ---
  if (effects.notificationText) {
    events.push({ type: 'consequence', message: effects.notificationText });
  }

  return { state: next, events };
}

/**
 * Login-based daily streak. Pure and deterministic (inject `now` in tests).
 *  - same calendar day as lastLoginDate  → unchanged
 *  - exactly the following day           → +1
 *  - a gap (or first login)              → reset to 1
 */
export function computeDailyStreak(
  state: PlayerState,
  now: Date = new Date()
): { dailyStreak: number; lastLoginDate: string; changed: boolean } {
  const todayStr = now.toISOString().split('T')[0];
  if (state.lastLoginDate === todayStr) {
    return { dailyStreak: state.dailyStreak, lastLoginDate: todayStr, changed: false };
  }
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  const yesterdayStr = yesterday.toISOString().split('T')[0];
  const dailyStreak = state.lastLoginDate === yesterdayStr ? state.dailyStreak + 1 : 1;
  return { dailyStreak, lastLoginDate: todayStr, changed: true };
}
