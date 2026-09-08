import { Book, Scene } from '../../types';
import { BOOK_1, SCENES as BOOK_1_SCENES } from './book1';

export const BOOKS: { [id: string]: Book } = {
  book1: BOOK_1,
};

export const ALL_SCENES: { [id: string]: Scene } = {
  ...BOOK_1_SCENES,
};

export function getSceneById(sceneId: string): Scene | null {
  return ALL_SCENES[sceneId] || null;
}

export function getBookById(bookId: string): Book | null {
  return BOOKS[bookId] || null;
}
