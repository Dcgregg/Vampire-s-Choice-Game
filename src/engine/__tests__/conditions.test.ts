import { describe, it, expect } from 'vitest';
import { evaluateCondition, isChoiceAvailable } from '../conditions';
import { SceneChoice } from '../../types';
import { baseState } from './helpers';

describe('conditions — flags', () => {
  it('undefined condition is always available', () => {
    expect(evaluateCondition(undefined, baseState()).available).toBe(true);
  });

  it('passes when required flag matches', () => {
    const state = baseState({ flags: { metLucian: true } });
    expect(evaluateCondition({ requiredFlags: { metLucian: true } }, state).available).toBe(true);
  });

  it('fails when required flag is missing / mismatched', () => {
    const res = evaluateCondition({ requiredFlags: { metLucian: true } }, baseState());
    expect(res.available).toBe(false);
    expect(res.reasons.length).toBeGreaterThan(0);
  });

  it('supports string/number flag values', () => {
    const state = baseState({ flags: { chosenPartner: 'lucian', rank: 3 } });
    expect(evaluateCondition({ requiredFlags: { chosenPartner: 'lucian', rank: 3 } }, state).available).toBe(true);
    expect(evaluateCondition({ requiredFlags: { chosenPartner: 'isolde' } }, state).available).toBe(false);
  });
});

describe('conditions — relationships', () => {
  it('legacy minRelationship passes at/above threshold', () => {
    // lucian starts at 50
    expect(evaluateCondition({ minRelationship: { characterId: 'lucian', minValue: 50 } }, baseState()).available).toBe(true);
  });

  it('legacy minRelationship fails below threshold', () => {
    expect(evaluateCondition({ minRelationship: { characterId: 'lucian', minValue: 60 } }, baseState()).available).toBe(false);
  });

  it('multiple relationship thresholds combine with AND', () => {
    const ok = evaluateCondition(
      { relationships: [{ characterId: 'lucian', min: 50 }, { characterId: 'isolde', min: 40 }] },
      baseState()
    );
    expect(ok.available).toBe(true); // isolde starts at 45
    const fail = evaluateCondition(
      { relationships: [{ characterId: 'lucian', min: 50 }, { characterId: 'isolde', min: 50 }] },
      baseState()
    );
    expect(fail.available).toBe(false);
  });

  it('max relationship bound works', () => {
    expect(evaluateCondition({ relationships: [{ characterId: 'marcella', max: 40 }] }, baseState()).available).toBe(true); // 35
    expect(evaluateCondition({ relationships: [{ characterId: 'marcella', max: 30 }] }, baseState()).available).toBe(false);
  });

  it('unknown character fails safe (unavailable)', () => {
    expect(evaluateCondition({ minRelationship: { characterId: 'ghost', minValue: 1 } }, baseState()).available).toBe(false);
  });
});

describe('conditions — currency / progress / identity', () => {
  it('currency bounds', () => {
    const state = baseState({ bloodCoins: 100 });
    expect(evaluateCondition({ minCoins: 100 }, state).available).toBe(true);
    expect(evaluateCondition({ minCoins: 101 }, state).available).toBe(false);
    expect(evaluateCondition({ maxCoins: 100 }, state).available).toBe(true);
    expect(evaluateCondition({ maxCoins: 99 }, state).available).toBe(false);
  });

  it('story progress: chapter, book, visitedScene', () => {
    const state = baseState({
      progress: {
        currentBookId: 'book1',
        currentChapter: 2,
        currentSceneId: 'b1_c2_s1',
        completedChapters: [1],
        completedBooks: [],
        sceneHistory: ['b1_c1_s1', 'b1_c2_s1'],
      },
    });
    expect(evaluateCondition({ requiredChapter: 2 }, state).available).toBe(true);
    expect(evaluateCondition({ requiredChapter: 3 }, state).available).toBe(false);
    expect(evaluateCondition({ requiredBook: 'book1' }, state).available).toBe(true);
    expect(evaluateCondition({ requiredBook: 'book2' }, state).available).toBe(false);
    expect(evaluateCondition({ visitedScene: 'b1_c1_s1' }, state).available).toBe(true);
    expect(evaluateCondition({ visitedScene: 'b1_c9_s9' }, state).available).toBe(false);
  });

  it('player identity: gender / orientation, incl. missing player', () => {
    const state = baseState();
    expect(evaluateCondition({ playerGender: 'Woman' }, state).available).toBe(true);
    expect(evaluateCondition({ playerGender: ['Man', 'Non-binary'] }, state).available).toBe(false);
    expect(evaluateCondition({ playerOrientation: ['Bisexual', 'Pansexual'] }, state).available).toBe(true);
    const noPlayer = baseState({ player: null });
    expect(evaluateCondition({ playerGender: 'Woman' }, noPlayer).available).toBe(false);
  });
});

describe('conditions — multiple mixed conditions (AND)', () => {
  it('all must pass', () => {
    const state = baseState({ flags: { metLucian: true }, bloodCoins: 200 });
    expect(
      evaluateCondition(
        { requiredFlags: { metLucian: true }, minCoins: 150, minRelationship: { characterId: 'lucian', minValue: 50 } },
        state
      ).available
    ).toBe(true);
    // one failing part fails the whole
    expect(
      evaluateCondition(
        { requiredFlags: { metLucian: true }, minCoins: 500 },
        state
      ).available
    ).toBe(false);
  });
});

describe('isChoiceAvailable wrapper', () => {
  it('locks a choice whose condition is unmet and unlocks when satisfied', () => {
    const choice: SceneChoice = {
      id: 'c', text: 't', nextSceneId: 'x',
      condition: { requiredFlags: { hasSilverKey: true } },
    };
    expect(isChoiceAvailable(choice, baseState())).toBe(false);
    expect(isChoiceAvailable(choice, baseState({ flags: { hasSilverKey: true } }))).toBe(true);
  });
});
