import { describe, it, expect } from 'vitest';
import { selectChoice } from '../engine';
import { getSceneById } from '../../data/story';
import { SceneChoice } from '../../types';
import { baseState } from './helpers';

describe('selectChoice — locking', () => {
  it('a choice whose conditions are unmet is NOT executable', () => {
    const state = baseState();
    const locked: SceneChoice = {
      id: 'locked', text: 't', nextSceneId: 'b1_c1_s2a',
      condition: { requiredFlags: { hasSilverKey: true } },
      effects: { coinsChange: 100 },
    };
    const res = selectChoice(state, locked, getSceneById);
    expect(res.ok).toBe(false);
    expect(res.reason).toBe('conditions_not_met');
    expect(res.state).toBe(state); // untouched
    expect(res.events).toEqual([]);
  });

  it('the same choice becomes executable once its condition is satisfied', () => {
    const state = baseState({ flags: { hasSilverKey: true }, bloodCoins: 0 });
    const choice: SceneChoice = {
      id: 'ok', text: 't', nextSceneId: 'b1_c1_s2a',
      condition: { requiredFlags: { hasSilverKey: true } },
      effects: { coinsChange: 100 },
    };
    const res = selectChoice(state, choice, getSceneById);
    expect(res.ok).toBe(true);
    expect(res.state.bloodCoins).toBe(100);
    expect(res.state.progress.currentSceneId).toBe('b1_c1_s2a');
  });
});

describe('selectChoice — full flow', () => {
  it('validates → applies effects → navigates in one step', () => {
    const state = baseState({ bloodCoins: 0 });
    const choice: SceneChoice = {
      id: 'c', text: 't', nextSceneId: 'b1_c1_s2a',
      effects: {
        relationshipChanges: { lucian: 6 },
        setFlags: { metLucian: true },
        achievementId: 'FIRST_CHOICE',
        coinsChange: 10,
        notificationText: 'noted',
      },
    };
    const res = selectChoice(state, choice, getSceneById);
    expect(res.ok).toBe(true);
    expect(res.state.relationships.lucian.affinity).toBe(56);
    expect(res.state.flags.metLucian).toBe(true);
    expect(res.state.bloodCoins).toBe(10);
    expect(res.state.achievements.FIRST_CHOICE.unlockedAt).toBeTruthy();
    expect(res.state.progress.currentSceneId).toBe('b1_c1_s2a');
    expect(res.events.some((e) => e.type === 'consequence')).toBe(true);
  });

  it('honours a returnToLanding choice', () => {
    const state = baseState({
      progress: {
        currentBookId: 'book1', currentChapter: 3, currentSceneId: 'b1_c3_s3',
        completedChapters: [1, 2], sceneHistory: [],
      },
    });
    const choice: SceneChoice = {
      id: 'end', text: 't', nextSceneId: 'b1_c3_s3', returnToLanding: true,
      effects: { coinsChange: 100, setFlags: { completedBook1: true } },
    };
    const res = selectChoice(state, choice, getSceneById);
    expect(res.ok).toBe(true);
    expect(res.returnToLanding).toBe(true);
    expect(res.state.flags.completedBook1).toBe(true);
    expect(res.state.progress.currentSceneId).toBe('b1_c3_s3'); // unchanged
  });
});
