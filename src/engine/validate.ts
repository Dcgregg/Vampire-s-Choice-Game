/**
 * Story Engine — Content validation.
 *
 * Detects malformed story content before it can break gameplay. Every issue
 * carries the affected book/chapter/scene/choice id for fast debugging. Pure
 * and side-effect free. Used by the Content Loader (strict) and optionally in
 * development to surface warnings.
 *
 * Checks: duplicate ids, missing/broken starting scene, dangling nextSceneId,
 * unknown character/achievement references, invalid condition/effect keys and
 * value types, invalid chapter references, and missing book metadata. Simple
 * unreachable-scene detection is included where reliably determinable.
 */
import { Achievement, Book, Character, Scene } from '../types';

export interface ContentIssue {
  level: 'error' | 'warning';
  message: string;
}

export interface ContentSources {
  scenes: { [id: string]: Scene };
  books: { [id: string]: Book };
  achievements: { [id: string]: Achievement };
  characters: { [id: string]: Character };
}

const VALID_CONDITION_KEYS = new Set([
  'requiredFlags', 'minRelationship', 'relationships', 'minCoins', 'maxCoins',
  'requiredBook', 'requiredChapter', 'visitedScene', 'playerGender',
  'playerOrientation', 'completedBook',
]);

const VALID_EFFECT_KEYS = new Set([
  'relationshipChanges', 'setFlags', 'coinsChange', 'streakIncrement',
  'achievementId', 'notificationText',
]);

export function validateContent(sources: ContentSources): ContentIssue[] {
  const { scenes, books, achievements, characters } = sources;
  const issues: ContentIssue[] = [];
  const err = (message: string) => issues.push({ level: 'error', message });
  const warn = (message: string) => issues.push({ level: 'warning', message });

  // ---- Books & chapters ----
  for (const book of Object.values(books)) {
    if (!book.id || !book.title) err(`Book "${book.id || '?'}": missing required metadata (id/title).`);
    if (!book.chapters || book.chapters.length === 0) {
      err(`Book "${book.id}": has no chapters.`);
      continue;
    }
    const chapterNumbers = new Set<number>();
    for (const chapter of book.chapters) {
      if (chapterNumbers.has(chapter.number)) err(`Book "${book.id}": duplicate chapter number ${chapter.number}.`);
      chapterNumbers.add(chapter.number);
      if (!scenes[chapter.firstSceneId]) {
        err(`Book "${book.id}" chapter ${chapter.number}: firstSceneId "${chapter.firstSceneId}" does not exist.`);
      }
      if (chapter.completionAchievementId && !achievements[chapter.completionAchievementId]) {
        warn(`Book "${book.id}" chapter ${chapter.number}: unknown completionAchievementId "${chapter.completionAchievementId}".`);
      }
    }
    if (book.startingSceneId && !scenes[book.startingSceneId]) {
      err(`Book "${book.id}": broken startingSceneId "${book.startingSceneId}".`);
    }
  }

  // ---- Scenes & choices ----
  const referencedSceneIds = new Set<string>();
  for (const book of Object.values(books)) {
    if (book.startingSceneId) referencedSceneIds.add(book.startingSceneId);
    for (const ch of book.chapters ?? []) referencedSceneIds.add(ch.firstSceneId);
  }

  for (const scene of Object.values(scenes)) {
    const loc = `Scene "${scene.id}"`;

    // Chapter reference: the scene's chapterNumber should exist in its book.
    const book = books[scene.bookId];
    if (book && book.chapters && !book.chapters.some((c) => c.number === scene.chapterNumber)) {
      warn(`${loc}: chapterNumber ${scene.chapterNumber} is not defined in book "${scene.bookId}".`);
    }

    if (!scene.choices || scene.choices.length === 0) {
      warn(`${loc}: has no choices (dead-end).`);
      continue;
    }

    for (const choice of scene.choices) {
      const cloc = `${loc} choice "${choice.id}"`;

      // Navigation: must resolve unless the choice ends the book.
      if (!choice.endsBook) {
        if (!choice.nextSceneId) err(`${cloc}: missing nextSceneId.`);
        else if (!scenes[choice.nextSceneId]) err(`${cloc}: nextSceneId "${choice.nextSceneId}" does not exist.`);
        else referencedSceneIds.add(choice.nextSceneId);
      }

      // Effects.
      if (choice.effects) {
        for (const key of Object.keys(choice.effects)) {
          if (!VALID_EFFECT_KEYS.has(key)) warn(`${cloc}: unknown effect key "${key}".`);
        }
        const e = choice.effects;
        if (e.achievementId && !achievements[e.achievementId]) {
          err(`${cloc}: unknown achievement "${e.achievementId}".`);
        }
        if (e.coinsChange !== undefined && typeof e.coinsChange !== 'number') {
          err(`${cloc}: coinsChange must be a number.`);
        }
        if (e.relationshipChanges) {
          for (const [cid, delta] of Object.entries(e.relationshipChanges)) {
            if (!characters[cid]) warn(`${cloc}: unknown character "${cid}" in relationshipChanges.`);
            if (typeof delta !== 'number') err(`${cloc}: relationshipChanges["${cid}"] must be a number.`);
          }
        }
      }

      // Conditions.
      if (choice.condition) {
        for (const key of Object.keys(choice.condition)) {
          if (!VALID_CONDITION_KEYS.has(key)) warn(`${cloc}: unknown condition key "${key}".`);
        }
        const c = choice.condition;
        if (c.minRelationship && !characters[c.minRelationship.characterId]) {
          warn(`${cloc}: unknown character "${c.minRelationship.characterId}" in minRelationship.`);
        }
        for (const r of c.relationships ?? []) {
          if (!characters[r.characterId]) warn(`${cloc}: unknown character "${r.characterId}" in relationships condition.`);
        }
        if (c.requiredBook && !books[c.requiredBook]) {
          warn(`${cloc}: requiredBook "${c.requiredBook}" is not a known book.`);
        }
      }
    }
  }

  // ---- Unreachable scenes (only when we have a starting point to anchor on) ----
  if (referencedSceneIds.size > 0) {
    for (const id of Object.keys(scenes)) {
      if (!referencedSceneIds.has(id)) {
        warn(`Scene "${id}": appears unreachable (not a starting scene and not referenced by any choice).`);
      }
    }
  }

  return issues;
}
