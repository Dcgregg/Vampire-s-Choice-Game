import { describe, it, expect } from 'vitest';
import { selectChoice } from '../engine';
import { getSceneById } from '../../data/story';
import { PlayerState, SceneChoice } from '../../types';
import { baseState } from './helpers';

function choiceOf(sceneId: string, choiceId: string): SceneChoice {
  const scene = getSceneById(sceneId);
  if (!scene) throw new Error(`scene ${sceneId} not found`);
  const choice = scene.choices.find((c) => c.id === choiceId);
  if (!choice) throw new Error(`choice ${choiceId} not found in ${sceneId}`);
  return choice;
}

describe('Book 1 — full playthrough regression (Lucian romance path)', () => {
  it('progresses through every chapter with correct state', () => {
    let state: PlayerState = baseState({
      progress: {
        currentBookId: 'book1', currentChapter: 1, currentSceneId: 'b1_c1_s1',
        completedChapters: [], completedBooks: [], sceneHistory: ['b1_c1_s1'],
      },
      bloodCoins: 250,
      dailyStreak: 3,
    });

    const path: [string, string][] = [
      ['b1_c1_s1', 'c1_pursue_shadow'],
      ['b1_c1_s2a', 'c2a_stand_ground'],
      ['b1_c1_s3', 'c3_blood_resonance'],
      ['b1_c1_s4', 'c4_accept_token'],
      ['b1_c2_s1', 'c2_1_crimson_mask'],
      ['b1_c2_s2', 'c2_2_dance_lucian'],
      ['b1_c2_s3', 'c2_3_expose_traitor'],
      ['b1_c2_s4', 'c2_4_embrace_destiny'],
      ['b1_c3_s1', 'c3_1_lead_charge'],
      ['b1_c3_s2', 'c3_2_vampire_embrace'],
    ];

    for (const [sceneId, choiceId] of path) {
      expect(state.progress.currentSceneId).toBe(sceneId);
      const res = selectChoice(state, choiceOf(sceneId, choiceId), getSceneById);
      expect(res.ok).toBe(true);
      state = res.state;
    }

    // Landed on the finale scene.
    expect(state.progress.currentSceneId).toBe('b1_c3_s3');
    expect(state.progress.currentChapter).toBe(3);

    // Chapter completion now populated as chapters were crossed.
    expect(state.progress.completedChapters).toEqual([1, 2]);

    // Currency total across the path (+15 +30 +50 +35 +60 +30 from 250).
    expect(state.bloodCoins).toBe(470);

    // Lucian affinity maxes out (clamped at 100).
    expect(state.relationships.lucian.affinity).toBe(100);
    expect(state.relationships.lucian.status).toBe('Devoted');

    // Key achievements unlocked along the way.
    const unlocked = Object.values(state.achievements).filter((a) => a.unlockedAt).map((a) => a.id);
    for (const id of ['FIRST_CHOICE', 'FIRST_BLOOD', 'DANGEROUS_LIAISON', 'SECRET_KEEPER', 'SHADOW_SOVEREIGN']) {
      expect(unlocked).toContain(id);
    }

    // Key flags set.
    expect(state.flags.metLucian).toBe(true);
    expect(state.flags.knowsVampireSecret).toBe(true);
    expect(state.flags.completedChapter1).toBe(true);
    expect(state.flags.chosenPartner).toBe('lucian');

    // Final choice completes the book explicitly (no loop back to scene 1).
    const finale = selectChoice(state, choiceOf('b1_c3_s3', 'c3_3_conclude_book1'), getSceneById);
    expect(finale.ok).toBe(true);
    expect(finale.bookCompleted).toBe('book1');
    expect(finale.state.progress.completedBooks).toContain('book1');
    expect(finale.state.bloodCoins).toBe(570);
    expect(finale.state.flags.completedBook1).toBe(true);
    // Progress is NOT reset to b1_c1_s1.
    expect(finale.state.progress.currentSceneId).toBe('b1_c3_s3');
  });

  it('supports the Isolde branch of chapter 1 as an alternate path', () => {
    let state = baseState();
    state = selectChoice(state, choiceOf('b1_c1_s1', 'c1_investigate_lectern'), getSceneById).state;
    expect(state.progress.currentSceneId).toBe('b1_c1_s2b');
    expect(state.flags.hasSilverKey).toBe(true);
    expect(state.relationships.isolde.affinity).toBe(51);
  });
});
