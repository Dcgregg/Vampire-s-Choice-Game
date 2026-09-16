/**
 * Phase 6A build-time generator.
 *
 * Regenerates the deterministic, versioned trusted-content artifacts consumed by
 * the Python authoritative reducer. Run: `yarn content:export`.
 *
 * Output (committed to the repo, treated as trusted by the backend):
 *   backend/trusted_content/registry.json         - trusted effects table + rules
 *   backend/trusted_content/parity_fixtures.json  - golden engine playthroughs
 *
 * The browser never supplies reward data at runtime; the server reads only these
 * generated files, which are derived solely from the authored content bundle.
 */
import { writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { buildRegistry, buildFixtures, stableStringify } from '../src/progression/trustedExport';

const here = dirname(fileURLToPath(import.meta.url));
const outDir = resolve(here, '../backend/trusted_content');
mkdirSync(outDir, { recursive: true });

const registryPath = resolve(outDir, 'registry.json');
const fixturesPath = resolve(outDir, 'parity_fixtures.json');

writeFileSync(registryPath, stableStringify(buildRegistry()));
writeFileSync(fixturesPath, stableStringify(buildFixtures()));

console.log('Wrote', registryPath);
console.log('Wrote', fixturesPath);
