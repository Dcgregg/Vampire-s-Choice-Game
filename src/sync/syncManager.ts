/**
 * Local-first cloud sync manager.
 *
 * Sits ABOVE local persistence: the game already saves to localStorage on every
 * change; this manager mirrors that state to the cloud when the backend is
 * reachable. It never blocks gameplay and never lives inside the Story Engine.
 *
 * Flow:  game state change -> local save (host) -> recordLocalSave() -> debounced push
 * Offline: push fails silently, status = 'offline', a retry is scheduled.
 * Conflict: a stale push gets 409; the manager adopts the newer cloud save
 *           (cloud wins for stale clients) and applies it to the game.
 */
import { PlayerState } from '../types';
import { getPlayerId } from './playerId';
import { getSave, putSave, CloudSave } from './cloudClient';
import { reconcileOnStart } from './reconcile';

const META_KEY = 'vc_sync_meta';

export type SyncStatus = 'idle' | 'syncing' | 'synced' | 'offline' | 'conflict' | 'error';

interface Attachment {
  getState: () => PlayerState;
  applyCloudState: (state: PlayerState) => void;
  migrate: (rawPlayerState: any) => PlayerState;
}

class SyncManager {
  private playerId = '';
  private cloudRevision = 0;
  private lastSyncedJson = '';
  private debounce: ReturnType<typeof setTimeout> | null = null;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private attached: Attachment | null = null;
  public status: SyncStatus = 'idle';

  attach(a: Attachment): void {
    this.attached = a;
    this.playerId = getPlayerId();
    this.loadMeta();
  }

  getPlayerId(): string {
    return this.playerId;
  }

  private loadMeta(): void {
    try {
      const m = JSON.parse(localStorage.getItem(META_KEY) || '{}');
      if (m.playerId === this.playerId && typeof m.revision === 'number') {
        this.cloudRevision = m.revision;
      }
    } catch {
      /* ignore */
    }
  }

  private saveMeta(): void {
    try {
      localStorage.setItem(META_KEY, JSON.stringify({ playerId: this.playerId, revision: this.cloudRevision }));
    } catch {
      /* ignore */
    }
  }

  /** Called once on app start: reconcile local vs cloud, then begin syncing. */
  async start(): Promise<void> {
    if (!this.attached) return;
    let cloud: CloudSave | null = null;
    try {
      cloud = await getSave(this.playerId);
    } catch {
      this.status = 'offline';
      this.scheduleRetry();
      this.scheduleSync();
      return;
    }

    const action = reconcileOnStart({
      localHasPlayer: !!this.attached.getState().player,
      cloud: cloud ? { revision: cloud.revision } : null,
    });

    if (action === 'adopt_cloud' && cloud) {
      this.adopt(cloud);
    } else if (action === 'push_create' || action === 'keep_local_push') {
      this.cloudRevision = cloud ? cloud.revision : 0;
      this.saveMeta();
      this.scheduleSync(0);
    }
    // 'noop': nothing local and nothing in cloud.
  }

  private adopt(cloud: CloudSave): void {
    if (!this.attached) return;
    const migrated = this.attached.migrate(cloud.playerState);
    this.cloudRevision = cloud.revision;
    this.lastSyncedJson = JSON.stringify(migrated);
    this.saveMeta();
    this.attached.applyCloudState(migrated);
    this.status = 'synced';
  }

  /** Host calls this after each local save; debounced to avoid chatty writes. */
  recordLocalSave(): void {
    this.scheduleSync();
  }

  private scheduleSync(delay = 1200): void {
    if (this.debounce) clearTimeout(this.debounce);
    this.debounce = setTimeout(() => void this.push(), delay);
  }

  private scheduleRetry(delay = 5000): void {
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.retryTimer = setTimeout(() => void this.push(), delay);
  }

  async push(): Promise<void> {
    if (!this.attached) return;
    const state = this.attached.getState();
    if (!state.player) return; // nothing meaningful to sync yet

    const json = JSON.stringify(state);
    if (json === this.lastSyncedJson) {
      this.status = 'synced';
      return; // skip cosmetic/navigation-only changes
    }

    this.status = 'syncing';
    try {
      const res = await putSave(this.playerId, {
        saveSchemaVersion: state.version,
        contentVersions: state.contentVersions || {},
        playerState: state,
        baseRevision: this.cloudRevision,
      });
      if (res.ok && res.save) {
        this.cloudRevision = res.save.revision;
        this.lastSyncedJson = json;
        this.saveMeta();
        this.status = 'synced';
        return;
      }
      // Conflict variant: cloud is newer than this client.
      const current = res.currentSave;
      if (current) {
        // Adopt the newer cloud save (a stale client cannot overwrite it).
        this.status = 'conflict';
        this.adopt(current);
      } else {
        this.status = 'error';
      }
    } catch {
      this.status = 'offline';
      this.scheduleRetry();
    }
  }
}

export const syncManager = new SyncManager();
