import { describe, it, expect } from 'vitest';
import {
  loadBook,
  loadSeries,
  loadAllContent,
  collectBookIssues,
  normalizeAndValidateBook,
  ContentValidationError,
} from '../../content/loader';
import { RawBookBundle } from '../../content/schema';
import book1Raw from '../../content/books/book1.json';

const raw = () => structuredClone(book1Raw) as unknown as RawBookBundle;

describe('content loader — happy path', () => {
  it('loads Book 1 with schema/version metadata parsed', () => {
    const loaded = loadBook('book1');
    expect(Object.keys(loaded.scenes)).toHaveLength(13);
    expect(loaded.book.title).toBe('Bloodlines of Blackthorn');
    expect(loaded.meta.contentSchemaVersion).toBe(1);
    expect(loaded.meta.bookVersion).toBe(1);
    expect(loaded.scenes[loaded.book.startingSceneId!]).toBeTruthy();
  });

  it('normalises a scene into the typed model (example)', () => {
    const { scenes } = loadBook('book1');
    const s = scenes['b1_c1_s1'];
    expect(Array.isArray(s.paragraphs)).toBe(true);
    expect(s.paragraphs.length).toBeGreaterThan(0);
    expect(Array.isArray(s.choices)).toBe(true);
    const first = s.choices.find((c) => c.id === 'c1_pursue_shadow')!;
    expect(first.nextSceneId).toBe('b1_c1_s2a');
    expect(first.effects?.achievementId).toBe('FIRST_CHOICE');
  });

  it('Book 1 loads into the same effective scene graph (parity)', () => {
    const { scenes } = loadBook('book1');
    const ids = Object.keys(scenes).sort();
    expect(ids).toEqual(
      [
        'b1_c1_s1', 'b1_c1_s2a', 'b1_c1_s2b', 'b1_c1_s2c', 'b1_c1_s3', 'b1_c1_s4',
        'b1_c2_s1', 'b1_c2_s2', 'b1_c2_s3', 'b1_c2_s4', 'b1_c3_s1', 'b1_c3_s2', 'b1_c3_s3',
      ].sort()
    );
    // Every non-ending choice resolves within the loaded graph.
    let endings = 0;
    for (const scene of Object.values(scenes)) {
      for (const c of scene.choices) {
        if (c.endsBook) { endings++; continue; }
        expect(scenes[c.nextSceneId], `${scene.id}/${c.id} -> ${c.nextSceneId}`).toBeTruthy();
      }
    }
    expect(endings).toBe(1); // exactly one book-ending choice
  });

  it('effects and conditions survive externalisation (spot checks)', () => {
    const { scenes } = loadBook('book1');
    const dance = scenes['b1_c2_s2'].choices.find((c) => c.id === 'c2_2_dance_lucian')!;
    expect(dance.effects?.achievementId).toBe('DANGEROUS_LIAISON');
    const lectern = scenes['b1_c1_s1'].choices.find((c) => c.id === 'c1_investigate_lectern')!;
    expect(lectern.effects?.setFlags?.hasSilverKey).toBe(true);
    const finale = scenes['b1_c3_s3'].choices.find((c) => c.id === 'c3_3_conclude_book1')!;
    expect(finale.endsBook).toBe(true);
  });

  it('series registry lists book1 available and book2 coming soon', () => {
    const series = loadSeries();
    expect(series.books.find((b) => b.id === 'book1')?.status).toBe('available');
    expect(series.books.find((b) => b.id === 'book2')?.status).toBe('coming_soon');
  });

  it('loadAllContent includes only available books', () => {
    const content = loadAllContent();
    expect(Object.keys(content.books)).toEqual(['book1']);
    expect(content.bookVersions.book1).toBe(1);
    expect(Object.keys(content.scenes)).toHaveLength(13);
  });
});

describe('content loader — rejects malformed content with useful errors', () => {
  it('valid bundle does not throw', () => {
    expect(() => normalizeAndValidateBook(raw())).not.toThrow();
  });

  it('dangling nextSceneId', () => {
    const bad = raw();
    bad.scenes[0].choices[0].nextSceneId = 'ghost_scene';
    const issues = collectBookIssues(bad);
    expect(issues.some((i) => i.level === 'error' && i.message.includes('ghost_scene'))).toBe(true);
    expect(() => normalizeAndValidateBook(bad)).toThrow(ContentValidationError);
  });

  it('duplicate scene id', () => {
    const bad = raw();
    bad.scenes.push({ ...bad.scenes[0] });
    const issues = collectBookIssues(bad);
    expect(issues.some((i) => i.message.toLowerCase().includes('duplicate'))).toBe(true);
  });

  it('unknown achievement reference', () => {
    const bad = raw();
    bad.scenes[0].choices[0].effects = { achievementId: 'NOPE' };
    expect(collectBookIssues(bad).some((i) => i.level === 'error' && i.message.includes('NOPE'))).toBe(true);
  });

  it('unknown character reference (warning)', () => {
    const bad = raw();
    bad.scenes[0].choices[0].effects = { relationshipChanges: { nobody: 5 } };
    expect(collectBookIssues(bad).some((i) => i.message.includes('nobody'))).toBe(true);
  });

  it('invalid effect key (warning)', () => {
    const bad = raw();
    (bad.scenes[0].choices[0].effects as any) = { bogusKey: 1 };
    expect(collectBookIssues(bad).some((i) => i.message.includes('bogusKey'))).toBe(true);
  });

  it('unsupported content schema version', () => {
    const bad = raw();
    bad.contentSchemaVersion = 99;
    expect(collectBookIssues(bad).some((i) => i.message.includes('contentSchemaVersion'))).toBe(true);
  });

  it('missing required book metadata', () => {
    const bad = raw();
    (bad.book as any).title = '';
    expect(collectBookIssues(bad).some((i) => i.message.toLowerCase().includes('metadata'))).toBe(true);
  });

  it('broken starting scene', () => {
    const bad = raw();
    bad.book.startingSceneId = 'nowhere';
    expect(collectBookIssues(bad).some((i) => i.message.includes('startingSceneId'))).toBe(true);
  });
});
