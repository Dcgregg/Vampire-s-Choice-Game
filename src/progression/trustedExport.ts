/**
 * Phase 6A — Trusted content export + parity harness (build-time, pure).
 *
 * SINGLE SOURCE OF TRUTH: the existing content bundle (content/books/*.json via
 * data/story). This module derives two deterministic, versioned artifacts that
 * the SERVER will trust — the browser never supplies reward data at runtime:
 *
 *   1. buildRegistry()  -> the "trusted content table": for each (book, version)
 *      every scene's choices and the authored economy/achievement effects, plus
 *      engine-derived rules (affinity clamp, derived-achievement thresholds,
 *      lifecycle awards) the reducer needs to reproduce rewards.
 *
 *   2. buildFixtures()  -> golden parity fixtures generated FROM the real TS
 *      Story Engine (applyEffects/unlockAchievement) over canonical playthroughs.
 *      The Python reducer must reproduce these exactly; the TS parity test pins
 *      the engine to the committed fixture. Together they stop the client engine
 *      and server reducer from silently diverging as future books are added.
 *
 * This file is imported ONLY by the export script and the parity tests. It is
 * not wired into the running application.
 */
import { PlayerState } from '../types';
import { BOOKS, ALL_SCENES, BOOK_VERSIONS } from '../data/story';
import { INITIAL_CHARACTERS } from '../data/characters';
import { INITIAL_ACHIEVEMENTS } from '../data/achievements';
import { CONTENT_SCHEMA_VERSION } from '../content/schema';
import { applyEffects, unlockAchievement } from '../engine/effects';

/** Engine-derived semantics that are logic (not authored content). Kept explicit
 *  in the trusted artifact so the Python reducer encodes identical rules. */
export const TRUSTED_RULES = {
  affinityMin: 0,
  affinityMax: 100,
  coinsMin: 0,
  /** Mirrors effects.ts: any relationship crossing the threshold unlocks it,
   *  evaluated only within a choice's relationship step. */
  derivedAchievements: [
    { id: 'DANGEROUS_LIAISON', type: 'affinityThreshold' as const, threshold: 70, scope: 'any' as const },
  ],
  /** Non-choice awards (mirrors GameStateManager.createCharacter). */
  lifecycleEvents: {
    character_created: { achievementId: 'THE_STORY_BEGINS' },
  },
};

interface TrustedChoice {
  nextSceneId: string;
  endsBook: boolean;
  effects: {
    coinsChange?: number;
    achievementId?: string;
    relationshipChanges?: { [characterId: string]: number };
    setFlags?: { [k: string]: boolean | string | number };
  };
  condition: unknown | null;
}

/** Pick only trusted, reward-relevant effect fields (drops UI-only notificationText). */
function trustedEffects(effects: any): TrustedChoice['effects'] {
  const out: TrustedChoice['effects'] = {};
  if (effects?.coinsChange !== undefined) out.coinsChange = effects.coinsChange;
  if (effects?.achievementId !== undefined) out.achievementId = effects.achievementId;
  if (effects?.relationshipChanges) out.relationshipChanges = effects.relationshipChanges;
  if (effects?.setFlags) out.setFlags = effects.setFlags;
  return out;
}

/** Build the versioned trusted-content registry from the bundled content. */
export function buildRegistry() {
  const characters: { [id: string]: number } = {};
  for (const [id, c] of Object.entries(INITIAL_CHARACTERS)) characters[id] = c.affinity;

  const books: Record<string, any> = {};
  for (const bookId of Object.keys(BOOKS)) {
    const book = BOOKS[bookId];
    const scenes: Record<string, any> = {};
    for (const scene of Object.values(ALL_SCENES)) {
      if (scene.bookId !== bookId) continue;
      const choices: Record<string, TrustedChoice> = {};
      for (const c of scene.choices) {
        choices[c.id] = {
          nextSceneId: c.nextSceneId,
          endsBook: !!c.endsBook,
          effects: trustedEffects(c.effects),
          condition: c.condition ?? null,
        };
      }
      scenes[scene.id] = { chapterNumber: scene.chapterNumber, choices };
    }
    books[bookId] = {
      version: BOOK_VERSIONS[bookId],
      startingSceneId: book.startingSceneId,
      scenes,
    };
  }

  return {
    contentSchemaVersion: CONTENT_SCHEMA_VERSION,
    rules: TRUSTED_RULES,
    knownAchievements: Object.keys(INITIAL_ACHIEVEMENTS),
    characters,
    books,
  };
}

// --------------------------- Parity fixtures ---------------------------

export interface CanonicalPath {
  book: string;
  version: number;
  /** [sceneId, choiceId] pairs following a legitimate authored route. */
  steps: [string, string][];
}

/** Canonical Book I playthrough to the Book Complete ending (+100). Exercises
 *  multiple coin awards, explicit achievements, relationship-derived unlocks
 *  and the endsBook choice. Mirrors the Book I completion regression path. */
export const CANONICAL_PATHS: CanonicalPath[] = [
  {
    book: 'book1',
    version: 1,
    steps: [
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
      ['b1_c3_s3', 'c3_3_conclude_book1'],
    ],
  },
];

function baseState(): PlayerState {
  const achievements: PlayerState['achievements'] = {};
  for (const [id, a] of Object.entries(INITIAL_ACHIEVEMENTS)) {
    achievements[id] = { ...a }; // locked: no unlockedAt
  }
  const relationships: PlayerState['relationships'] = {};
  for (const [id, c] of Object.entries(INITIAL_CHARACTERS)) relationships[id] = { ...c };
  return {
    player: null,
    relationships,
    flags: {},
    progress: {
      currentBookId: 'book1', currentChapter: 1, currentSceneId: 'b1_c1_s1',
      completedChapters: [], completedBooks: [], sceneHistory: [],
    },
    bloodCoins: 0, // isolate event-derived value from the (6B) opening grant
    dailyStreak: 0,
    lastLoginDate: '',
    achievements,
    settings: { fontSize: 'normal', ambientAudio: true, reducedMotion: false, highContrast: false },
    version: 3,
  };
}

function unlockedIds(state: PlayerState): string[] {
  return Object.values(state.achievements)
    .filter((a) => a.unlockedAt)
    .map((a) => a.id)
    .sort();
}

export interface FixtureStep {
  event: string;
  fromScene?: string;
  coins: number;
  achievements: string[];
}
export interface Fixture {
  book: string;
  version: number;
  startCoins: number;
  steps: FixtureStep[];
}

/** Replay a canonical path through the REAL engine to produce the golden truth. */
function buildOneFixture(path: CanonicalPath): Fixture {
  let state = baseState();
  // Lifecycle: character creation unlocks THE_STORY_BEGINS (engine-parity).
  state = unlockAchievement(state, TRUSTED_RULES.lifecycleEvents.character_created.achievementId).state;
  const steps: FixtureStep[] = [
    { event: 'character_created', coins: state.bloodCoins, achievements: unlockedIds(state) },
  ];
  for (const [sceneId, choiceId] of path.steps) {
    const scene = ALL_SCENES[sceneId];
    const choice = scene?.choices.find((c) => c.id === choiceId);
    if (!choice) throw new Error(`canonical path references missing choice ${sceneId}/${choiceId}`);
    state = applyEffects(state, choice.effects).state;
    steps.push({ event: choiceId, fromScene: sceneId, coins: state.bloodCoins, achievements: unlockedIds(state) });
  }
  return { book: path.book, version: path.version, startCoins: 0, steps };
}

export function buildFixtures(): Fixture[] {
  return CANONICAL_PATHS.map(buildOneFixture);
}

/** Deterministic JSON with recursively sorted keys (stable artifact bytes). */
export function stableStringify(value: unknown): string {
  const sort = (v: any): any => {
    if (Array.isArray(v)) return v.map(sort);
    if (v && typeof v === 'object') {
      return Object.keys(v).sort().reduce((acc: any, k) => { acc[k] = sort(v[k]); return acc; }, {});
    }
    return v;
  };
  return JSON.stringify(sort(value), null, 2) + '\n';
}
