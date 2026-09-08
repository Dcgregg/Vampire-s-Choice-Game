/**
 * Story Engine — Content validation.
 *
 * Basic integrity checks over authored content so mistakes surface early
 * instead of failing silently at runtime (e.g. a typo'd nextSceneId dumping the
 * player into the "shadows have closed" fallback). Pure and side-effect free;
 * the host may run it in development and log the results.
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

export function validateContent(sources: ContentSources): ContentIssue[] {
  const { scenes, books, achievements, characters } = sources;
  const issues: ContentIssue[] = [];

  // Every book's chapters must point at existing first scenes.
  for (const book of Object.values(books)) {
    for (const chapter of book.chapters) {
      if (!scenes[chapter.firstSceneId]) {
        issues.push({
          level: 'error',
          message: `Book "${book.id}" chapter ${chapter.number} firstSceneId "${chapter.firstSceneId}" does not exist.`,
        });
      }
      if (chapter.completionAchievementId && !achievements[chapter.completionAchievementId]) {
        issues.push({
          level: 'warning',
          message: `Book "${book.id}" chapter ${chapter.number} references unknown achievement "${chapter.completionAchievementId}".`,
        });
      }
    }
  }

  for (const scene of Object.values(scenes)) {
    for (const choice of scene.choices) {
      // Navigation links must resolve (unless the choice returns to landing).
      if (!choice.returnToLanding && !scenes[choice.nextSceneId]) {
        issues.push({
          level: 'error',
          message: `Scene "${scene.id}" choice "${choice.id}" nextSceneId "${choice.nextSceneId}" does not exist.`,
        });
      }
      // Referenced achievements must exist.
      const achId = choice.effects?.achievementId;
      if (achId && !achievements[achId]) {
        issues.push({
          level: 'error',
          message: `Scene "${scene.id}" choice "${choice.id}" references unknown achievement "${achId}".`,
        });
      }
      // Relationship effects/conditions must reference known characters.
      const relIds = [
        ...Object.keys(choice.effects?.relationshipChanges ?? {}),
        ...(choice.condition?.minRelationship ? [choice.condition.minRelationship.characterId] : []),
        ...(choice.condition?.relationships ?? []).map((r) => r.characterId),
      ];
      for (const cid of relIds) {
        if (!characters[cid]) {
          issues.push({
            level: 'warning',
            message: `Scene "${scene.id}" choice "${choice.id}" references unknown character "${cid}".`,
          });
        }
      }
    }
  }

  return issues;
}
