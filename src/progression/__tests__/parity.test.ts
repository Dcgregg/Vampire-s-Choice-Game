import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { buildRegistry, buildFixtures, stableStringify } from '../trustedExport';

const here = dirname(fileURLToPath(import.meta.url));
const trustedDir = resolve(here, '../../../backend/trusted_content');
const readJson = (name: string) => JSON.parse(readFileSync(resolve(trustedDir, name), 'utf-8'));

describe('Phase 6A trusted-content export parity', () => {
  it('committed registry.json matches buildRegistry() (regen enforced on content change)', () => {
    expect(readJson('registry.json')).toEqual(buildRegistry());
  });

  it('committed parity_fixtures.json matches the engine playthrough', () => {
    // Pins the TS Story Engine to the committed golden fixtures; the Python
    // reducer is checked against the same fixtures in test_reducer_parity.py.
    expect(readJson('parity_fixtures.json')).toEqual(buildFixtures());
  });

  it('export is deterministic (stable, sorted-key bytes)', () => {
    const a = stableStringify(buildRegistry());
    const b = stableStringify(buildRegistry());
    expect(a).toBe(b);
    expect(readFileSync(resolve(trustedDir, 'registry.json'), 'utf-8')).toBe(a);
  });

  it('every awarded achievement id is a known trusted id', () => {
    const reg = buildRegistry();
    const known = new Set(reg.knownAchievements);
    for (const d of reg.rules.derivedAchievements) expect(known.has(d.id)).toBe(true);
    for (const rule of Object.values(reg.rules.lifecycleEvents)) expect(known.has(rule.achievementId)).toBe(true);
    for (const book of Object.values<any>(reg.books)) {
      for (const scene of Object.values<any>(book.scenes)) {
        for (const choice of Object.values<any>(scene.choices)) {
          const aid = choice.effects?.achievementId;
          if (aid) expect(known.has(aid)).toBe(true);
        }
      }
    }
  });
});
