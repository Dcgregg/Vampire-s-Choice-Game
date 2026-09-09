import { describe, it, expect, beforeEach } from 'vitest';
import { getPlayerId } from '../playerId';
import { reconcileOnStart, resolvePushOutcome } from '../reconcile';

class FakeStorage {
  private m = new Map<string, string>();
  getItem(k: string) { return this.m.has(k) ? this.m.get(k)! : null; }
  setItem(k: string, v: string) { this.m.set(k, v); }
}

describe('anonymous player id', () => {
  let store: FakeStorage;
  beforeEach(() => { store = new FakeStorage(); });

  it('creates a vc_-prefixed non-PII id and persists it', () => {
    const id = getPlayerId(store);
    expect(id).toMatch(/^vc_[A-Za-z0-9_-]{8,64}$/);
    expect(store.getItem('vc_player_id')).toBe(id);
  });

  it('returns the same id on subsequent calls', () => {
    const a = getPlayerId(store);
    const b = getPlayerId(store);
    expect(a).toBe(b);
  });

  it('regenerates when the stored id is malformed', () => {
    store.setItem('vc_player_id', 'not-valid');
    const id = getPlayerId(store);
    expect(id).toMatch(/^vc_/);
    expect(id).not.toBe('not-valid');
  });
});

describe('reconcileOnStart (start-up matrix)', () => {
  it('local only -> push_create', () => {
    expect(reconcileOnStart({ localHasPlayer: true, cloud: null })).toBe('push_create');
  });
  it('nothing anywhere -> noop', () => {
    expect(reconcileOnStart({ localHasPlayer: false, cloud: null })).toBe('noop');
  });
  it('cloud only -> adopt_cloud', () => {
    expect(reconcileOnStart({ localHasPlayer: false, cloud: { revision: 3 } })).toBe('adopt_cloud');
  });
  it('both present -> keep_local_push', () => {
    expect(reconcileOnStart({ localHasPlayer: true, cloud: { revision: 2 } })).toBe('keep_local_push');
  });
});

describe('resolvePushOutcome (optimistic concurrency)', () => {
  it('no server save yet -> accept', () => {
    expect(resolvePushOutcome(0, null)).toBe('accept');
  });
  it('identical / local-newer (base == server) -> accept', () => {
    expect(resolvePushOutcome(2, 2)).toBe('accept');
  });
  it('cloud newer (base < server) -> reject_adopt_server', () => {
    expect(resolvePushOutcome(1, 5)).toBe('reject_adopt_server');
  });
  it('stale client -> reject_adopt_server', () => {
    expect(resolvePushOutcome(3, 4)).toBe('reject_adopt_server');
  });
});
