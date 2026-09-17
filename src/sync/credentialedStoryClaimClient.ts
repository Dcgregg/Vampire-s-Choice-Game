import { API_BASE } from './config';
import type { StoryAccountSave, StoryClaimResult } from './storyClaimClient';

/** Opt-in client only. Never obtain proof from a player ID or legacy save. */
function isStoryAccountSave(value: unknown): value is StoryAccountSave {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;
  const save = value as Record<string, unknown>;
  const object = (v: unknown) => v !== null && typeof v === 'object' && !Array.isArray(v);
  return !('playerId' in save) && !('userId' in save) && !('_id' in save) &&
    Number.isSafeInteger(save.saveSchemaVersion) && (save.saveSchemaVersion as number) > 0 &&
    object(save.contentVersions) && object(save.playerState) &&
    Number.isSafeInteger(save.revision) && (save.revision as number) > 0 &&
    typeof save.createdAt === 'string' && typeof save.updatedAt === 'string';
}

/** The credential is a bearer secret; callers must retrieve it from secure issuance, not infer it. */
export async function claimStoryWithCredential(
  playerId: string, expectedAnonymousRevision: number, claimCredential: string,
): Promise<StoryClaimResult> {
  if (!/^vc_[A-Za-z0-9_-]{8,64}$/.test(playerId) ||
      !Number.isSafeInteger(expectedAnonymousRevision) || expectedAnonymousRevision < 1 ||
      !/^[A-Za-z0-9_-]{43}$/.test(claimCredential)) {
    return { ok: false, kind: 'invalid_request' };
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/me/claim-story-with-credential`, {
      method: 'POST', credentials: 'include', cache: 'no-store',
      headers: { 'Content-Type': 'application/json', 'X-Anonymous-Claim-Credential': claimCredential },
      body: JSON.stringify({ playerId, expectedAnonymousRevision }),
    });
  } catch {
    return { ok: false, kind: 'unavailable' };
  }
  const body: unknown = await response.json().catch(() => null);
  if (response.ok) return isStoryAccountSave(body)
    ? { ok: true, save: body } : { ok: false, kind: 'unavailable' };
  if (response.status === 401) return { ok: false, kind: 'unauthenticated' };
  if (response.status === 403) return { ok: false, kind: 'denied' };
  if (response.status === 409 && body !== null && typeof body === 'object' &&
      'detail' in body && body.detail !== null && typeof body.detail === 'object' &&
      'error' in body.detail && body.detail.error === 'claim_conflict') {
    return { ok: false, kind: 'conflict', resolution: 'review_existing_progress_or_retry' };
  }
  if (response.status === 422) return { ok: false, kind: 'invalid_request' };
  return { ok: false, kind: 'unavailable' };
}
