/**
 * Content layer — schema & version metadata.
 *
 * These describe the RAW shape of the bundled content files (JSON today, but
 * could be an API/DB/CMS tomorrow). The Content Loader converts these raw
 * bundles into the engine's typed Book/Scene model, so the Story Engine never
 * knows or cares where content came from.
 *
 * Versioning is deliberately layered and kept separate from player-save
 * versioning (see utils/storage.ts SAVE_SCHEMA_VERSION):
 *   - CONTENT_SCHEMA_VERSION : structural shape of the content files themselves.
 *   - book.version           : revision of an individual book's authored content.
 *   - (player) save schema    : lives in PlayerState.version — NOT here.
 */
import { Book, Scene, SeriesBookRef } from '../types';

/** Structural version of the content-file format. Bump on breaking shape changes. */
export const CONTENT_SCHEMA_VERSION = 1;

/** Raw JSON shape of a single book bundle (book metadata + its scenes). */
export interface RawBookBundle {
  contentSchemaVersion: number;
  book: Book & {
    version: number;
    seriesId: string;
    order: number;
    startingSceneId: string;
  };
  scenes: Scene[];
}

/** Raw JSON shape of the series registry. */
export interface RawSeries {
  contentSchemaVersion: number;
  series: {
    id: string;
    title: string;
    description: string;
    books: SeriesBookRef[];
  };
}

/** Result of loading + validating + normalising one raw book bundle. */
export interface LoadedBook {
  book: Book;
  scenes: { [id: string]: Scene };
  meta: {
    contentSchemaVersion: number;
    bookVersion: number;
    seriesId: string;
  };
}
