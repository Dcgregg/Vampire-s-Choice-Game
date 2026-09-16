import { PlayerState } from '../types';
import { getPlayerId } from './playerId';
import { getSave, putSave, getAccountSave, putAccountSave, CloudSave } from './cloudClient';
import { reconcileOnStart } from './reconcile';

const META_KEY = 'vc_sync_meta';
export type SyncStatus = 'idle' | 'syncing' | 'synced' | 'offline' | 'conflict' | 'error';
type Mode = 'anonymous' | 'account';

interface Attachment {
  getState: () => PlayerState;
  applyCloudState: (state: PlayerState) => void;
  migrate: (rawPlayerState: any) => PlayerState;
}

class SyncManager {
  private playerId = '';
  private cloudRevision = 0;
  private lastSyncedJson = '';
  private mode: Mode = 'anonymous';
  private debounce: ReturnType<typeof setTimeout> | null = null;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private attached: Attachment | null = null;
  private listeners = new Set<(s: SyncStatus) => void>();
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
    this.setStatus('idle');
  }

  recordLocalSave(): void { this.scheduleSync(); }
  private scheduleSync(delay = 1200): void { if (this.debounce) clearTimeout(this.debounce); this.debounce = setTimeout(() => void this.push(), delay); }
  private scheduleRetry(delay = 5000): void { if (this.retryTimer) clearTimeout(this.retryTimer); this.retryTimer = setTimeout(() => void this.push(), delay); }

  async push(): Promise<void> {
    if (!this.attached) return;
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
      if (current) { this.setStatus('conflict'); this.adopt(current); } else { this.setStatus('error'); }
    } catch { this.setStatus('offline'); this.scheduleRetry(); }
  }
}

export const syncManager = new SyncManager();
