import type { PlayerState } from '../types';

export function buildProgressShareText(state: PlayerState, appUrl: string): string {
  const chapter = Math.max(1, state.progress.currentChapter);
  const scenes = state.progress.sceneHistory.length;
  const completedBooks = state.progress.completedBooks.length;
  const progress = completedBooks > 0
    ? `I've completed ${completedBooks} ${completedBooks === 1 ? 'book' : 'books'} and reached Chapter ${chapter}`
    : `I'm on Chapter ${chapter} after exploring ${scenes} ${scenes === 1 ? 'scene' : 'scenes'}`;

  return `${progress} in Vampire's Choice: Bloodlines of Blackthorn. Can you find your path through Blackthorn Academy? ${appUrl}`;
}

export type ShareProgressResult = 'shared' | 'copied' | 'cancelled';

export async function shareProgress(state: PlayerState): Promise<ShareProgressResult> {
  const text = buildProgressShareText(state, window.location.origin);
  if (typeof navigator.share === 'function') {
    try {
      await navigator.share({ title: "Vampire's Choice", text });
      return 'shared';
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return 'cancelled';
      throw error;
    }
  }
  await navigator.clipboard.writeText(text);
  return 'copied';
}
