import { PlayerState } from '../types';
import { getPlayerId } from './playerId';
import { getSave, putSave, getAccountSave, putAccountSave, CloudSave } from './cloudClient';
import { reconcileOnStart } from './reconcile';

const META_KEY = 'vc_sync_meta';
export type SyncStatus = 'idle' | 'syncing' | 'synced' | 'offline' | 'conflict' | 'error';
type Mode = 'anonymous' | 'account';

/** An unsynced local save that lost a revision race with the server on PUSH.
 *  Both versions are held so the player can choose which to keep. */
export interface PushConflict { local: PlayerState; cloud: CloudSave; }

interface Attachment {
  getState: () => PlayerState;
  applyCloudState: (state: PlayerState) => void;
  migrate: (rawPlayerState: any) => PlayerState;
}

export class SyncManager {
  private playerId = '';
  private cloudRevision = 0;
  private lastSyncedJson = '';
  private mode: Mode = 'anonymous';
  private debounce: ReturnType<typeof setTimeout> | null = null;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private attached: Attachment | null = null;
  private listeners = new Set<(s: SyncStatus) => void>();
  private pushConflict: PushConflict | null = null;
  private conflictListeners = new Set<(c: PushConflict | null) => void>();
  private resolving = false;
  public status: SyncStatus = 'idle';

  attach(a: Attachment): void {
    this.attached = a;
    this.playerId = getPlayerId();
    this.loadMeta();
  }

  getPlayerId(): string { return this.playerId; }
  getMode(): Mode { return this.mode; }

  subscribe(l: (s: SyncStatus) => void): () => void {
    this.listeners.add(l);
    l(this.status);
    return () => this.listeners.delete(l);
  }
  private setStatus(s: SyncStatus): void { this.status = s; this.listeners.forEach((l) => l(s)); }

  /** Subscribe to outstanding PUSH conflicts (both local + cloud preserved). */
  subscribeConflict(l: (c: PushConflict | null) => void): () => void {
    this.conflictListeners.add(l);
    l(this.pushConflict);
    return () => this.conflictListeners.delete(l);
  }
  getPushConflict(): PushConflict | null { return this.pushConflict; }
  private setConflict(c: PushConflict | null): void {
    this.pushConflict = c;
    this.conflictListeners.forEach((l) => l(c));
  }
  private cancelTimers(): void {
    if (this.debounce) { clearTimeout(this.debounce); this.debounce = null; }
    if (this.retryTimer) { clearTimeout(this.retryTimer); this.retryTimer = null; }
  }

  private loadMeta(): void {
    try {
      const m = JSON.parse(localStorage.getItem(META_KEY) || '{}');
      if (m.playerId === this.playerId && typeof m.revision === 'number') this.cloudRevision = m.revision;
    } catch { /* ignore */ }
  }
  private saveMeta(): void {
    try { localStorage.setItem(META_KEY, JSON.stringify({ playerId: this.playerId, revision: this.cloudRevision, mode: this.mode })); } catch { /* ignore */ }
  }

  async start(): Promise<void> {
    if (!this.attached || this.mode === 'account') return;
    let cloud: CloudSave | null = null;
    try { cloud = await getSave(this.playerId); }
    catch { this.setStatus('offline'); this.scheduleRetry(); this.scheduleSync(); return; }
    const action = reconcileOnStart({ localHasPlayer: !!this.attached.getState().player, cloud: cloud ? { revision: cloud.revision } : null });
    if (action === 'adopt_cloud' && cloud) this.adopt(cloud);
    else if (action === 'push_create' || action === 'keep_local_push') { this.cloudRevision = cloud ? cloud.revision : 0; this.saveMeta(); this.scheduleSync(0); }
  }

  private adopt(cloud: CloudSave): void {
    if (!this.attached) return;
    const migrated = this.attached.migrate(cloud.playerState);
    this.cloudRevision = cloud.revision;
    this.lastSyncedJson = JSON.stringify(migrated);
    this.saveMeta();
    this.attached.applyCloudState(migrated);
    this.setStatus('synced');
  }

  /** Switch to authenticated account persistence, adopting the account save. */
  enterAccountMode(save: CloudSave | null): void {
    this.mode = 'account';
    if (save) { this.cloudRevision = save.revision; this.adopt(save); }
    else { this.cloudRevision = 0; this.lastSyncedJson = ''; this.setStatus('idle'); this.scheduleSync(0); }
    this.saveMeta();
  }
  /** Return to anonymous persistence (logout). Keeps current local state. */
  exitAccountMode(): void {
    this.mode = 'anonymous';
    this.cloudRevision = 0;
    this.lastSyncedJson = '';
    this.setConflict(null);
    this.setStatus('idle');
  }

  recordLocalSave(): void { this.scheduleSync(); }
  private scheduleSync(delay = 1200): void {
    if (this.pushConflict) return; // never auto-push while a conflict awaits the player
    if (this.debounce) clearTimeout(this.debounce);
    this.debounce = setTimeout(() => void this.push(), delay);
  }
  private scheduleRetry(delay = 5000): void {
    if (this.pushConflict) return;
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.retryTimer = setTimeout(() => void this.push(), delay);
  }

  async push(): Promise<void> {
    if (!this.attached) return;
    if (this.pushConflict) return; // block auto-push until the player resolves it
    const state = this.attached.getState();
    if (!state.player) return;
    const json = JSON.stringify(state);
    if (json === this.lastSyncedJson) { this.setStatus('synced'); return; }
    this.setStatus('syncing');
    const payload = { saveSchemaVersion: state.version, contentVersions: state.contentVersions || {}, playerState: state, baseRevision: this.cloudRevision };
    try {
      const res = this.mode === 'account' ? await putAccountSave(payload) : await putSave(this.playerId, payload);
      if (res.ok && res.save) {
        this.cloudRevision = res.save.revision; this.lastSyncedJson = json; this.saveMeta(); this.setStatus('synced');
        return;
      }
      const current = res.currentSave;
      if (current) {
        // The server revision advanced. NEVER discard the unsynced local save:
        // preserve both and enter an explicit conflict for the player to resolve.
        this.cancelTimers();
        this.setConflict({ local: state, cloud: current });
        this.setStatus('conflict');
      } else {
        this.setStatus('error');
      }
    } catch { this.setStatus('offline'); this.scheduleRetry(); }
  }

  /**
   * Resolve an outstanding PUSH conflict by explicit player choice.
   *  - 'local': keep this device's progress; re-push it against the latest
   *    cloud revision. Only marks synced once the server confirms.
   *  - 'cloud': replace local with the cloud save (UI must confirm first).
   * Returns true on success; on failure both saves are preserved and the
   * conflict remains open so the player can retry.
   */
  async resolvePushConflict(choice: 'local' | 'cloud'): Promise<boolean> {
    const conflict = this.pushConflict;
    if (!conflict || this.resolving || !this.attached) return false;
    this.resolving = true;
    try {
      if (choice === 'cloud') {
        this.cloudRevision = conflict.cloud.revision;
        this.setConflict(null);
        this.adopt(conflict.cloud); // applies cloud, persists, sets synced
        return true;
      }
      // keep device: re-push current local state at the latest known cloud revision.
      this.setStatus('syncing');
      const state = this.attached.getState();
      const json = JSON.stringify(state);
      const payload = { saveSchemaVersion: state.version, contentVersions: state.contentVersions || {}, playerState: state, baseRevision: conflict.cloud.revision };
      const res = this.mode === 'account' ? await putAccountSave(payload) : await putSave(this.playerId, payload);
      if (res.ok && res.save) {
        this.cloudRevision = res.save.revision; this.lastSyncedJson = json; this.saveMeta();
        this.setConflict(null); this.setStatus('synced');
        return true;
      }
      if (res.currentSave) {
        // Another writer advanced again: keep both, refresh the cloud snapshot.
        this.setConflict({ local: state, cloud: res.currentSave });
        this.setStatus('conflict');
      } else {
        this.setStatus('error');
      }
      return false;
    } catch {
      // Network/server failure: keep both versions, allow retry.
      this.setStatus('offline');
      return false;
    } finally {
      this.resolving = false;
    }
  }
}

export const syncManager = new SyncManager();
