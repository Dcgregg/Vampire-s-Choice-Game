/**
 * Content Loader — the boundary between stored content and the Story Engine.
 *
 *   Content files (JSON)  ->  loadBook / loadAllContent
 *                          ->  validation + normalisation
 *                          ->  typed Book / Scene model
 *                          ->  Story Engine (consumes typed model only)
 *
 * The engine imports the typed model via data/story; it does NOT import JSON.
 * To swap the source for an API/DB/CMS later, only this file changes.
 */
import { Book, Scene, Series } from '../types';
import { INITIAL_CHARACTERS } from '../data/characters';
import { INITIAL_ACHIEVEMENTS } from '../data/achievements';
import { validateContent, ContentIssue } from '../engine';
import { CONTENT_SCHEMA_VERSION, LoadedBook, RawBookBundle, RawSeries } from './schema';
import book1Raw from './books/book1.json';
import seriesRaw from './series.json';

/** Thrown when a book fails validation in strict mode. Lists every issue. */
export class ContentValidationError extends Error {
  issues: ContentIssue[];
  constructor(bookId: string, issues: ContentIssue[]) {
    super(
      `Content validation failed for book "${bookId}":\n` +
        issues.map((i) => `  [${i.level}] ${i.message}`).join('\n')
    );
    this.name = 'ContentValidationError';
    this.issues = issues;
  }
}

/** Registry of raw bundles. Add future books here (or fetch them). */
const BUNDLES: { [id: string]: RawBookBundle } = {
  book1: book1Raw as unknown as RawBookBundle,
};

/** Light normalisation: guarantee arrays exist so the engine can trust shape. */
function normalizeScene(raw: Scene): Scene {
  return {
    ...raw,
    paragraphs: raw.paragraphs ?? [],
    choices: (raw.choices ?? []).map((c) => ({ ...c })),
  };
}

interface BuildResult {
  book: Book;
  scenes: { [id: string]: Scene };
  meta: LoadedBook['meta'];
  issues: ContentIssue[];
}

/** Normalise a raw bundle and collect all validation issues (does not throw). */
function buildBook(bundle: RawBookBundle): BuildResult {
  const bookId = bundle.book?.id ?? '?';
  const issues: ContentIssue[] = [];

  if (bundle.contentSchemaVersion !== CONTENT_SCHEMA_VERSION) {
    issues.push({
      level: 'error',
      message: `Book "${bookId}": contentSchemaVersion ${bundle.contentSchemaVersion} is not supported (expected ${CONTENT_SCHEMA_VERSION}).`,
    });
  }

  const scenes: { [id: string]: Scene } = {};
  const seen = new Set<string>();
  for (const raw of bundle.scenes ?? []) {
    if (seen.has(raw.id)) {
      issues.push({ level: 'error', message: `Book "${bookId}": duplicate scene id "${raw.id}".` });
    }
    seen.add(raw.id);
    scenes[raw.id] = normalizeScene(raw);
  }

  const book: Book = { ...bundle.book };

  issues.push(
    ...validateContent({
      scenes,
      books: { [book.id]: book },
      achievements: INITIAL_ACHIEVEMENTS,
      characters: INITIAL_CHARACTERS,
    })
  );

  if (!book.id || !book.title) {
    issues.push({ level: 'error', message: `Book "${bookId}": missing required metadata (id/title).` });
  }
  const start = bundle.book?.startingSceneId;
  if (!start || !scenes[start]) {
    issues.push({ level: 'error', message: `Book "${bookId}": broken startingSceneId "${start}".` });
  }

  return {
    book,
    scenes,
    meta: {
      contentSchemaVersion: bundle.contentSchemaVersion,
      bookVersion: bundle.book?.version,
      seriesId: bundle.book?.seriesId,
    },
    issues,
  };
}

/** Test/tooling helper: get validation issues for a raw bundle without throwing. */
export function collectBookIssues(bundle: RawBookBundle): ContentIssue[] {
  return buildBook(bundle).issues;
}

export interface LoadBookOptions {
  /** Throw on validation errors (default true). */
  strict?: boolean;
}

/** Normalise + validate a raw bundle into the typed model. */
export function normalizeAndValidateBook(
  bundle: RawBookBundle,
  options: LoadBookOptions = {}
): LoadedBook {
  const strict = options.strict ?? true;
  const { book, scenes, meta, issues } = buildBook(bundle);
  if (strict && issues.some((i) => i.level === 'error')) {
    throw new ContentValidationError(book.id, issues);
  }
  return { book, scenes, meta };
}

/** Load, validate and normalise a single registered book. */
export function loadBook(bookId: string, options: LoadBookOptions = {}): LoadedBook {
  const bundle = BUNDLES[bookId];
  if (!bundle) throw new Error(`Unknown book "${bookId}"`);
  return normalizeAndValidateBook(bundle, options);
}

/** Load the series registry (which books exist and their availability). */
export function loadSeries(): Series {
  const raw = seriesRaw as unknown as RawSeries;
  return {
    id: raw.series.id,
    title: raw.series.title,
    description: raw.series.description,
    books: raw.series.books,
  };
}

export interface LoadedContent {
  series: Series;
  books: { [id: string]: Book };
  scenes: { [id: string]: Scene };
  bookVersions: { [id: string]: number };
}

/** Load every AVAILABLE book in the series into a single typed content set. */
export function loadAllContent(): LoadedContent {
  const series = loadSeries();
  const books: { [id: string]: Book } = {};
  const scenes: { [id: string]: Scene } = {};
  const bookVersions: { [id: string]: number } = {};

  for (const ref of series.books) {
    if (ref.status !== 'available') continue;
    const loaded = loadBook(ref.id);
    books[ref.id] = loaded.book;
    Object.assign(scenes, loaded.scenes);
    bookVersions[ref.id] = loaded.meta.bookVersion;
  }

  return { series, books, scenes, bookVersions };
}
