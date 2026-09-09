/**
 * Anonymous player identity.
 *
 * A stable, non-PII id used only as the KEY for a player's cloud save. It is
 * generated locally and persisted in localStorage. It is NOT authentication and
 * MUST NOT be trusted for future security/purchase-sensitive operations.
 *
 * Limitation: an id stored on a single browser/device provides cloud
 * persistence for that identity only. It does NOT provide reliable cross-device
 * account recovery — that requires a future authenticated account, at which
 * point this anonymous id can be linked to the account (see docs/persistence.md).
 */
const KEY = 'vc_player_id';
const ID_RE = /^vc_[A-Za-z0-9_-]{8,64}$/;

interface StorageLike {
  getItem(k: string): string | null;
  setItem(k: string, v: string): void;
}

function generateId(): string {
  const uuid =
    globalThis.crypto?.randomUUID?.().replace(/-/g, '') ??
    `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
  return `vc_${uuid}`.slice(0, 40);
}

export function getPlayerId(storage: StorageLike | undefined = safeLocalStorage()): string {
  let existing: string | null = null;
  try {
    existing = storage?.getItem(KEY) ?? null;
  } catch {
    existing = null;
  }
  if (existing && ID_RE.test(existing)) return existing;

  const id = generateId();
  try {
    storage?.setItem(KEY, id);
  } catch {
    /* storage unavailable — id is still returned for this session */
  }
  return id;
}

function safeLocalStorage(): StorageLike | undefined {
  try {
    return globalThis.localStorage;
  } catch {
    return undefined;
  }
}
