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
