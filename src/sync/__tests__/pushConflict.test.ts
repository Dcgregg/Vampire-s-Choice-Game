import { describe, it, expect, beforeEach, vi } from 'vitest';

// Mock the network layer so we can drive PUSH results deterministically.
const putAccountSave = vi.fn();
const putSave = vi.fn();
const getSave = vi.fn();
const getAccountSave = vi.fn();
vi.mock('../cloudClient', () => ({
  getSave: (...a: any[]) => getSave(...a),
  putSave: (...a: any[]) => putSave(...a),
  getAccountSave: (...a: any[]) => getAccountSave(...a),
  putAccountSave: (...a: any[]) => putAccountSave(...a),
}));

import { SyncManager } from '../syncManager';

const cloudSave = (revision: number, chapter: number) => ({
  playerId: 'vc_test', saveSchemaVersion: 3, contentVersions: {}, revision,
  playerState: { player: { name: 'E' }, progress: { currentBookId: 'book1', currentChapter: chapter }, version: 3 },
  createdAt: '', updatedAt: '',
});

const localState = (chapter: number) => ({ player: { name: 'E' }, progress: { currentBookId: 'book1', currentChapter: chapter }, version: 3 } as any);

/** Build an account-mode manager synced at cloud rev1/ch1, then diverge locally. */
function setup(localChapter = 2) {
  const box = { current: localState(1) as any };
  const sm = new SyncManager();
  sm.attach({
    getState: () => box.current,
    applyCloudState: (s) => { box.current = s; },
    migrate: (raw) => raw,
  });
  sm.enterAccountMode(cloudSave(1, 1)); // local == cloud rev1 (ch1), lastSynced set
  box.current = localState(localChapter); // unsynced local edit -> ch2
  return { sm, box };
}

beforeEach(() => { putAccountSave.mockReset(); putSave.mockReset(); getSave.mockReset(); getAccountSave.mockReset(); });

describe('PUSH conflict never discards unsynced local progress', () => {
  it('a 409 enters conflict and preserves BOTH versions', async () => {
    const { sm, box } = setup(2);
    putAccountSave.mockResolvedValueOnce({ ok: false, currentSave: cloudSave(2, 9) });
    await sm.push();
    expect(sm.status).toBe('conflict');
    const c = sm.getPushConflict();
    expect(c).not.toBeNull();
    expect(c!.local.progress.currentChapter).toBe(2);   // device version held
    expect(c!.cloud.revision).toBe(2);                  // cloud version held
    expect(c!.cloud.playerState.progress.currentChapter).toBe(9);
    // local was NOT overwritten with cloud (ch9)
    expect(box.current.progress.currentChapter).toBe(2);
  });

  it('does not auto-push while a conflict is outstanding', async () => {
    const { sm } = setup(2);
    putAccountSave.mockResolvedValueOnce({ ok: false, currentSave: cloudSave(2, 9) });
    await sm.push();
    putAccountSave.mockClear();
    sm.recordLocalSave();      // would normally schedule a background push
    await sm.push();           // explicit call must also early-return
    expect(putAccountSave).not.toHaveBeenCalled();
    expect(sm.getPushConflict()).not.toBeNull();
  });

  it('keep-device retries against the latest cloud revision and only then marks synced', async () => {
    const { sm, box } = setup(2);
    putAccountSave.mockResolvedValueOnce({ ok: false, currentSave: cloudSave(2, 9) });
    await sm.push();
    putAccountSave.mockResolvedValueOnce({ ok: true, save: cloudSave(3, 2) });
    const ok = await sm.resolvePushConflict('local');
    expect(ok).toBe(true);
    expect(sm.getPushConflict()).toBeNull();
    expect(sm.status).toBe('synced');
    expect(putAccountSave.mock.calls.at(-1)![0].baseRevision).toBe(2); // used cloud rev as base
    expect(box.current.progress.currentChapter).toBe(2);               // device content kept
  });

  it('keep-cloud replaces local with the cloud save', async () => {
    const { sm, box } = setup(2);
    putAccountSave.mockResolvedValueOnce({ ok: false, currentSave: cloudSave(2, 9) });
    await sm.push();
    const ok = await sm.resolvePushConflict('cloud');
    expect(ok).toBe(true);
    expect(sm.getPushConflict()).toBeNull();
    expect(sm.status).toBe('synced');
    expect(box.current.progress.currentChapter).toBe(9); // adopted cloud
  });

  it('a SECOND conflict during keep-device resolution keeps both and stays in conflict', async () => {
    const { sm, box } = setup(2);
    putAccountSave.mockResolvedValueOnce({ ok: false, currentSave: cloudSave(2, 9) });
    await sm.push();
    putAccountSave.mockResolvedValueOnce({ ok: false, currentSave: cloudSave(3, 11) });
    const ok = await sm.resolvePushConflict('local');
    expect(ok).toBe(false);
    const c = sm.getPushConflict();
    expect(c).not.toBeNull();
    expect(c!.cloud.revision).toBe(3);                    // refreshed cloud snapshot
    expect(sm.status).toBe('conflict');
    expect(box.current.progress.currentChapter).toBe(2);  // local still intact
  });

  it('a network failure during resolution preserves both versions and allows retry', async () => {
    const { sm, box } = setup(2);
    putAccountSave.mockResolvedValueOnce({ ok: false, currentSave: cloudSave(2, 9) });
    await sm.push();
    putAccountSave.mockRejectedValueOnce(new Error('network'));
    const ok = await sm.resolvePushConflict('local');
    expect(ok).toBe(false);
    expect(sm.getPushConflict()).not.toBeNull(); // both kept
    expect(sm.status).toBe('offline');
    expect(box.current.progress.currentChapter).toBe(2);
    // retry now succeeds
    putAccountSave.mockResolvedValueOnce({ ok: true, save: cloudSave(3, 2) });
    const ok2 = await sm.resolvePushConflict('local');
    expect(ok2).toBe(true);
    expect(sm.getPushConflict()).toBeNull();
    expect(sm.status).toBe('synced');
  });

  it('logout clears any outstanding conflict', async () => {
    const { sm } = setup(2);
    putAccountSave.mockResolvedValueOnce({ ok: false, currentSave: cloudSave(2, 9) });
    await sm.push();
    expect(sm.getPushConflict()).not.toBeNull();
    sm.exitAccountMode();
    expect(sm.getPushConflict()).toBeNull();
  });
});
