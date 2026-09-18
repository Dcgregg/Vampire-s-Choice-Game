import { beforeEach, describe, expect, it, vi } from 'vitest';

const recordChoice = vi.hoisted(() => vi.fn());

vi.hoisted(() => {
  const store = new Map<string, string>();
  (globalThis as any).localStorage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value),
    removeItem: (key: string) => void store.delete(key),
    clear: () => store.clear(),
  };
});

vi.mock('../../progression/trustedProgressionQueue', () => ({
  trustedProgressionQueue: { recordChoice },
}));
vi.mock('../../utils/audio', () => ({
  gothicAudio: {
    playChoiceChime() {}, playAchievementChime() {}, playAtmosphere() {}, stopAtmosphere() {},
  },
}));
vi.mock('../../sync/syncManager', () => ({
  syncManager: { attach() {}, async start() {}, recordLocalSave() {} },
}));

import { GameStateManager } from '../gameState';
import { getSceneById } from '../../data/story';

const openingChoice = () => getSceneById('b1_c1_s1')!.choices[0];

describe('GameStateManager trusted choice capture', () => {
  beforeEach(() => {
    localStorage.clear();
    recordChoice.mockReset();
  });

  it('captures only choice identity and checkpoint before local narration advances', () => {
    recordChoice.mockReturnValue(true);
    const game = new GameStateManager();
    game.createCharacter('Elena', 'Woman', 'Bisexual');
    const choice = openingChoice();

    game.makeChoice(choice);

    expect(recordChoice).toHaveBeenCalledWith({
      bookId: 'book1',
      contentVersion: 1,
      fromSceneId: 'b1_c1_s1',
      choiceId: choice.id,
    });
    expect(recordChoice.mock.calls[0][0]).not.toHaveProperty('effects');
    expect(recordChoice.mock.calls[0][0]).not.toHaveProperty('coins');
    expect(game.getState().progress.currentSceneId).toBe(choice.nextSceneId);
  });

  it('does not advance local narration when authoritative capture is blocked', () => {
    recordChoice.mockReturnValue(false);
    const game = new GameStateManager();
    game.createCharacter('Elena', 'Woman', 'Bisexual');

    game.makeChoice(openingChoice());

    expect(game.getState().progress.currentSceneId).toBe('b1_c1_s1');
  });
});

