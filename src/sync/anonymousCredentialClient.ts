import { API_BASE } from './config';
import type { CloudSave } from './cloudClient';

/** A fresh identity is returned once; never reconstruct proof from a legacy player ID. */
export type AnonymousCredentialIssueResult =
  | { ok: true; save: CloudSave; claimCredential: string }
  | { ok: false; kind: 'unavailable' | 'invalid_response' };

const record = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);

function validSave(value: unknown): value is CloudSave {
  if (!record(value)) return false;
  if (!/^vc_[A-Za-z0-9_-]{8,64}$/.test(String(value.playerId ?? ''))) return false;
  if ('_id' in value || 'claimCredentialDigest' in value || 'claimedBy' in value || 'userId' in value) return false;
  if (!Number.isSafeInteger(value.saveSchemaVersion) || (value.saveSchemaVersion as number) < 1 ||
      !Number.isSafeInteger(value.revision) || value.revision !== 1 ||
      !record(value.contentVersions) || !record(value.playerState) ||
      typeof value.createdAt !== 'string' || !value.createdAt ||
      typeof value.updatedAt !== 'string' || !value.updatedAt) return false;
  return Object.values(value.contentVersions).every(
    version => Number.isSafeInteger(version) && (version as number) >= 1,
  );
}

/**
 * Opt-in only: do not call from the legacy anonymous save flow. The caller must
 * explicitly adopt both values together, with a reviewed credential storage and
 * recovery policy. Never log, put in a URL, or send the secret to legacy PUT.
 */
export async function issueAnonymousCredential(): Promise<AnonymousCredentialIssueResult> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/anonymous/credentialed-save`, {
      method: 'POST',
      credentials: 'omit',
      headers: { 'Content-Type': 'application/json' },
      cache: 'no-store',
      body: '{}',
    });
  } catch {
    return { ok: false, kind: 'unavailable' };
  }
  if (response.status !== 201) return { ok: false, kind: 'unavailable' };
  const body: unknown = await response.json().catch(() => null);
  if (!record(body) || !validSave(body.save) ||
      typeof body.claimCredential !== 'string' ||
      !/^[A-Za-z0-9_-]{43}$/.test(body.claimCredential)) {
    return { ok: false, kind: 'invalid_response' };
  }
  return { ok: true, save: body.save, claimCredential: body.claimCredential };
}
