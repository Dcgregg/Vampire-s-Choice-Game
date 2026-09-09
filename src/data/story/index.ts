/**
 * Typed content access for the Story Engine and UI.
 *
 * This module is the ONLY place the app reaches for story content. It delegates
 * to the Content Loader (content/loader.ts), which reads the bundled JSON,
 * validates + normalises it, and returns the typed Book/Scene model. Swapping
 * the content source (API/DB/CMS) later means changing only the loader.
 */
import { Book, Scene, Series } from '../../types';
import { loadAllContent } from '../../content/loader';

const content = loadAllContent();

export const SERIES: Series = content.series;
export const BOOKS: { [id: string]: Book } = content.books;
export const ALL_SCENES: { [id: string]: Scene } = content.scenes;
/** Authored content revision per available book (persisted onto new saves). */
export const BOOK_VERSIONS: { [id: string]: number } = content.bookVersions;

export function getSceneById(sceneId: string): Scene | null {
  return ALL_SCENES[sceneId] || null;
}

export function getBookById(bookId: string): Book | null {
  return BOOKS[bookId] || null;
}
