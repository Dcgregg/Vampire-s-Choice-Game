import { describe, it, expect } from 'vitest';
import {
  applyEffects,
  unlockAchievement,
  computeDailyStreak,
  updateRelationshipStatus,
} from '../effects';
import { baseState } from './helpers';

describe('effects — relationships', () => {
  it('applies delta, clamps 0..100 and recomputes status without mutating input', () => {
    const state = baseState();
    const before = state.relationships.lucian.affinity;
    const { state: next } = applyEffects(state, { relationshipChanges: { lucian: 40 } });
    expect(next.relationships.lucian.affinity).toBe(before + 40); // 90
    expect(next.relationships.lucian.status).toBe('Devoted');
    // input untouched
    expect(state.relationships.lucian.affinity).toBe(before);
  });

  it('clamps negative deltas at 0 and marks Rival', () => {
    const { state } = applyEffects(baseState(), { relationshipChanges: { lucian: -999 } });
    expect(state.relationships.lucian.affinity).toBe(0);
    expect(state.relationships.lucian.status).toBe('Rival');
  });

  it('unlocks DANGEROUS_LIAISON when crossing the intensity threshold (>=70)', () => {
    const { state, events } = applyEffects(baseState(), { relationshipChanges: { lucian: 30 } }); // 50 -> 80
    expect(state.achievements.DANGEROUS_LIAISON.unlockedAt).toBeTruthy();
    expect(events.some((e) => e.type === 'achievementUnlocked' && e.achievementId === 'DANGEROUS_LIAISON')).toBe(true);
  });

  it('emits relationshipChanged events', () => {
    const { events } = applyEffects(baseState(), { relationshipChanges: { isolde: 5 } });
    expect(events).toContainEqual({ type: 'relationshipChanged', characterId: 'isolde', delta: 5, newAffinity: 50 });
  });
});

describe('effects — flags / currency / streak / notification', () => {
  it('merges flags', () => {
    const { state } = applyEffects(baseState({ flags: { a: true } }), { setFlags: { b: 'x', c: 2 } });
    expect(state.flags).toEqual({ a: true, b: 'x', c: 2 });
  });

  it('adds coins and emits event', () => {
    const { state, events } = applyEffects(baseState({ bloodCoins: 100 }), { coinsChange: 25 });
    expect(state.bloodCoins).toBe(125);
    expect(events).toContainEqual({ type: 'coinsChanged', delta: 25, total: 125 });
  });

  it('never lets coins go below zero', () => {
    const { state } = applyEffects(baseState({ bloodCoins: 10 }), { coinsChange: -9999 });
    expect(state.bloodCoins).toBe(0);
  });

  it('honours explicit streakIncrement effect', () => {
    const { state, events } = applyEffects(baseState({ dailyStreak: 3 }), { streakIncrement: true });
    expect(state.dailyStreak).toBe(4);
    expect(events).toContainEqual({ type: 'streakChanged', value: 4 });
  });

  it('emits a consequence event for notificationText', () => {
    const { events } = applyEffects(baseState(), { notificationText: 'Lucian noticed you.' });
    expect(events).toContainEqual({ type: 'consequence', message: 'Lucian noticed you.' });
  });

  it('no effects => no change, no events', () => {
    const state = baseState();
    const res = applyEffects(state, undefined);
    expect(res.state).toBe(state);
    expect(res.events).toEqual([]);
  });
});

describe('effects — achievements', () => {
  it('unlocks an explicit achievement once (idempotent)', () => {
    const first = applyEffects(baseState(), { achievementId: 'FIRST_CHOICE' });
    expect(first.state.achievements.FIRST_CHOICE.unlockedAt).toBeTruthy();
    expect(first.events.some((e) => e.type === 'achievementUnlocked')).toBe(true);
    const second = applyEffects(first.state, { achievementId: 'FIRST_CHOICE' });
    expect(second.events.some((e) => e.type === 'achievementUnlocked')).toBe(false);
  });

  it('unlockAchievement is pure and idempotent', () => {
    const state = baseState();
    const a = unlockAchievement(state, 'SECRET_KEEPER');
    expect(a.event).toBeTruthy();
    expect(state.achievements.SECRET_KEEPER.unlockedAt).toBeUndefined(); // input untouched
    const b = unlockAchievement(a.state, 'SECRET_KEEPER');
    expect(b.event).toBeUndefined();
  });
});

describe('effects — status thresholds & daily streak', () => {
  it('updateRelationshipStatus boundaries', () => {
    expect(updateRelationshipStatus(0)).toBe('Rival');
    expect(updateRelationshipStatus(25)).toBe('Rival');
    expect(updateRelationshipStatus(26)).toBe('Acquaintance');
    expect(updateRelationshipStatus(50)).toBe('Intrigued');
    expect(updateRelationshipStatus(65)).toBe('Trusted');
    expect(updateRelationshipStatus(85)).toBe('Devoted');
  });

  it('computeDailyStreak: same day unchanged, next day +1, gap resets to 1', () => {
    const state = baseState({ dailyStreak: 5, lastLoginDate: '2026-01-10' });
    expect(computeDailyStreak(state, new Date('2026-01-10T09:00:00Z'))).toEqual({ dailyStreak: 5, lastLoginDate: '2026-01-10', changed: false });
    expect(computeDailyStreak(state, new Date('2026-01-11T09:00:00Z'))).toEqual({ dailyStreak: 6, lastLoginDate: '2026-01-11', changed: true });
    expect(computeDailyStreak(state, new Date('2026-01-15T09:00:00Z'))).toEqual({ dailyStreak: 1, lastLoginDate: '2026-01-15', changed: true });
  });
});
