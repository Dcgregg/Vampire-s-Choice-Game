import { describe, it, expect, vi, beforeEach } from 'vitest';

// Minimal in-memory localStorage for the node test env (hoisted before imports)
// so GameStateManager's save/load round-trips cleanly without console noise.
vi.hoisted(() => {
  const store = new Map<string, string>();
  (globalThis as any).localStorage = {
    getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
    setItem: (k: string, v: string) => void store.set(k, String(v)),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
    key: () => null,
    get length() { return store.size; },
  };
});

// Neutralise browser/network-only side effects so the real GameStateManager can
// run in the node test environment. Progression logic (engine + Book I content)
// and the screen-resolution logic under test are NOT mocked.
vi.mock('../../utils/audio', () => ({
  gothicAudio: {
    playChoiceChime() {}, playAchievementChime() {}, playAtmosphere() {}, stopAtmosphere() {},
  },
}));
vi.mock('../../sync/syncManager', () => ({
  syncManager: {
    attach() {}, async start() {}, recordLocalSave() {}, exitAccountMode() {}, getPlayerId: () => 'vc_test',
  },
}));

import { GameStateManager } from '../gameState';
import { getSceneById } from '../../data/story';
import { SceneChoice } from '../../types';

function choiceOf(sceneId: string, choiceId: string): SceneChoice {
  const scene = getSceneById(sceneId);
  if (!scene) throw new Error(`scene ${sceneId} not found`);
  const choice = scene.choices.find((c) => c.id === choiceId);
  if (!choice) throw new Error(`choice ${choiceId} not found in ${sceneId}`);
  return choice;
}

// A valid Book I playthrough (Lucian romance path) up to the finale reading scene.
const PATH: [string, string][] = [
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
const FINALE_SCENE = 'b1_c3_s3';
const FINALE_CHOICE = 'c3_3_conclude_book1';

describe('Book I completion — app resolves to the Book Complete screen (regression)', () => {
  let gm: GameStateManager;
  beforeEach(() => { (globalThis as any).localStorage.clear(); gm = new GameStateManager(); });

  it('a full playthrough marks book1 complete and shows book_complete, without reopening the finale', () => {
    gm.createCharacter('Elena', 'Woman', 'Bisexual');
    expect(gm.activeScreen).toBe('reading');
    expect(gm.getState().progress.currentSceneId).toBe('b1_c1_s1');

    // Walk the authored path through every chapter to the finale reading scene.
    for (const [sceneId, choiceId] of PATH) {
      expect(gm.getState().progress.currentSceneId).toBe(sceneId);
      gm.makeChoice(choiceOf(sceneId, choiceId));
    }
    expect(gm.getState().progress.currentSceneId).toBe(FINALE_SCENE);
    // On the finale reading scene the book is not yet complete: still reading.
    expect(gm.getState().progress.completedBooks).not.toContain('book1');
    expect(gm.activeScreen).toBe('reading');

    // The book-ending choice records completion and resolves to the Book Complete screen.
    gm.makeChoice(choiceOf(FINALE_SCENE, FINALE_CHOICE));
    expect(gm.activeScreen).toBe('book_complete');
    expect(gm.getState().progress.completedBooks).toContain('book1');
    // The finale is NOT reopened / reset to the opening scene.
    expect(gm.getState().progress.currentSceneId).toBe(FINALE_SCENE);
    expect(gm.getState().progress.currentSceneId).not.toBe('b1_c1_s1');
  });

  it('resuming a completed book routes to book_complete, never back into the finale as unfinished', () => {
    gm.createCharacter('Elena', 'Woman', 'Bisexual');
    for (const [sceneId, choiceId] of PATH) gm.makeChoice(choiceOf(sceneId, choiceId));
    gm.makeChoice(choiceOf(FINALE_SCENE, FINALE_CHOICE));
    expect(gm.getState().progress.completedBooks).toContain('book1');

    // Navigate away, then hit "Continue" like a returning player.
    gm.setScreen('landing');
    expect(gm.activeScreen).toBe('landing');
    gm.continueStory();

    expect(gm.activeScreen).toBe('book_complete');   // resolves to completion...
    expect(gm.activeScreen).not.toBe('reading');     // ...never the unfinished finale
    expect(gm.getState().progress.currentSceneId).toBe(FINALE_SCENE);
  });
});
