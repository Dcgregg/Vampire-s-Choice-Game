/**
 * Thin HTTP client for the cloud save API. All calls fail loudly (throw) on
 * network/unknown errors so the sync manager can treat the backend as
 * unavailable and keep the game running on local storage.
 */
import { API_BASE } from './config';

export interface CloudSave {
  playerId: string;
  saveSchemaVersion: number;
  contentVersions: { [bookId: string]: number };
  playerState: any;
  revision: number;
  createdAt: string;
  updatedAt: string;
}

export interface SavePayload {
  saveSchemaVersion: number;
  contentVersions: { [bookId: string]: number };
  playerState: any;
  baseRevision: number;
}

export async function health(): Promise<boolean> {
  try {
    const r = await fetch(`${API_BASE}/health`);
    return r.ok;
  } catch {
    return false;
  }
}

export async function getSave(playerId: string): Promise<CloudSave | null> {
  const r = await fetch(`${API_BASE}/saves/${playerId}`);
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`getSave failed: ${r.status}`);
  return (await r.json()) as CloudSave;
}

export interface PutResult {
  ok: boolean;
  save?: CloudSave;
  currentSave?: CloudSave | null;
}

export async function putSave(playerId: string, payload: SavePayload): Promise<PutResult> {
  const r = await fetch(`${API_BASE}/saves/${playerId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (r.status === 409) {
    const body = await r.json().catch(() => ({}));
    return { ok: false, currentSave: body.currentSave ?? null };
  }
  if (!r.ok) throw new Error(`putSave failed: ${r.status}`);
  return { ok: true, save: (await r.json()) as CloudSave };
}

// ---- Authenticated (account) endpoints — rely on the httpOnly session cookie ----
export interface PublicUser { email: string; name: string; picture?: string | null; }

export async function getMe(): Promise<PublicUser | null> {
  const r = await fetch(`${API_BASE}/auth/me`, { credentials: 'include' });
  if (!r.ok) return null;
  return (await r.json()) as PublicUser;
}

export async function logoutApi(): Promise<void> {
  try { await fetch(`${API_BASE}/auth/logout`, { method: 'POST', credentials: 'include' }); } catch { /* ignore */ }
}

export async function getAccountSave(): Promise<CloudSave | null> {
  const r = await fetch(`${API_BASE}/me/save`, { credentials: 'include' });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`getAccountSave failed: ${r.status}`);
  return (await r.json()) as CloudSave;
}

export async function putAccountSave(payload: SavePayload): Promise<PutResult> {
  const r = await fetch(`${API_BASE}/me/save`, {
    method: 'PUT', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (r.status === 409) {
    const body = await r.json().catch(() => ({}));
    return { ok: false, currentSave: body.currentSave ?? null };
  }
  if (!r.ok) throw new Error(`putAccountSave failed: ${r.status}`);
  return { ok: true, save: (await r.json()) as CloudSave };
}

export type ClaimResult =
  | { ok: true; save: CloudSave }
  | { ok: false; conflict: true; accountSave: CloudSave; anonymousSave: any }
  | { ok: false; error: string };

export async function claimSave(playerId: string, strategy?: 'use_account' | 'use_anonymous'): Promise<ClaimResult> {
  const r = await fetch(`${API_BASE}/me/claim`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ playerId, strategy }),
  });
  if (r.ok) return { ok: true, save: (await r.json()) as CloudSave };
  const body = await r.json().catch(() => ({}));
  if (r.status === 409 && body.error === 'claim_conflict') {
    return { ok: false, conflict: true, accountSave: body.accountSave, anonymousSave: body.anonymousSave };
  }
  return { ok: false, error: (body.detail && body.detail.error) || body.error || `http_${r.status}` };
}
