import { API_BASE } from './config';
import type { CloudSave } from './cloudClient';

export type StoryClaimResult =
  | { ok: true; save: CloudSave }
  | { ok: false; kind: 'conflict'; resolution: 'review_existing_progress_or_retry'; reason?: string }
  | { ok: false; kind: 'denied' | 'unauthenticated' | 'invalid_request' | 'unavailable' };

/**
 * Opt-in Phase 6B client for the isolated story-only claim route.
 *
 * Deliberately not used by AuthContext yet. The account identity is never sent
 * by the browser; the server derives it from the authenticated session cookie.
 * The caller must supply the exact anonymous cloud-save revision it observed.
 */
export async function claimStoryOnly(
  playerId: string,
  expectedAnonymousRevision: number,
): Promise<StoryClaimResult> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/me/claim-story-only`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ playerId, expectedAnonymousRevision }),
    });
  } catch {
    return { ok: false, kind: 'unavailable' };
  }

  const body = await response.json().catch(() => ({}));
  if (response.ok) return { ok: true, save: body as CloudSave };
  if (response.status === 401) return { ok: false, kind: 'unauthenticated' };
  if (response.status === 403) return { ok: false, kind: 'denied' };
  if (response.status === 409 && body?.detail?.error === 'claim_conflict') {
    return {
      ok: false,
      kind: 'conflict',
      resolution: 'review_existing_progress_or_retry',
      reason: typeof body.detail.reason === 'string' ? body.detail.reason : undefined,
    };
  }
  if (response.status === 422) return { ok: false, kind: 'invalid_request' };
  return { ok: false, kind: 'unavailable' };
}
