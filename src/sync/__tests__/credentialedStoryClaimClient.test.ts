import { afterEach, describe, expect, it, vi } from 'vitest';
import { claimStoryWithCredential } from '../credentialedStoryClaimClient';

const credential = 'A'.repeat(43);
const response = (status: number, body: unknown) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json' },
});
const save = { saveSchemaVersion: 3, contentVersions: {}, playerState: { progress: {} },
  revision: 1, createdAt: 'now', updatedAt: 'now' };
afterEach(() => vi.unstubAllGlobals());

describe('claimStoryWithCredential', () => {
  it('sends proof in a header only, with cookie authentication', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(200, save));
    vi.stubGlobal('fetch', fetchMock);
    expect(await claimStoryWithCredential('vc_abcdefgh', 2, credential)).toEqual({ ok: true, save });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).not.toContain(credential);
    expect(init.credentials).toBe('include');
    expect(init.headers['X-Anonymous-Claim-Credential']).toBe(credential);
    expect(JSON.parse(init.body)).toEqual({ playerId: 'vc_abcdefgh', expectedAnonymousRevision: 2 });
    expect(init.body).not.toContain(credential);
    expect(init.body).not.toContain('userId');
  });

  it.each([null, {}, { ...save, revision: 0 }, { ...save, playerId: 'vc_abcdefgh' },
    { ...save, playerState: null }, { ...save, userId: 'other' }])(
    'rejects malformed successful response without entering account mode', async (body) => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(200, body)));
      expect(await claimStoryWithCredential('vc_abcdefgh', 2, credential)).toEqual({ ok: false, kind: 'unavailable' });
    },
  );

  it('fails closed before fetch on missing or malformed proof', async () => {
    const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
    expect(await claimStoryWithCredential('vc_abcdefgh', 2, '')).toEqual({ ok: false, kind: 'invalid_request' });
    expect(await claimStoryWithCredential('vc_abcdefgh', 0, credential)).toEqual({ ok: false, kind: 'invalid_request' });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('maps conflict without leaking either save or secret', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(409, {
      detail: { error: 'claim_conflict', accountSave: save, claimCredential: credential },
    })));
    expect(await claimStoryWithCredential('vc_abcdefgh', 2, credential)).toEqual({
      ok: false, kind: 'conflict', resolution: 'review_existing_progress_or_retry',
    });
  });

  it('does not echo a credential on network failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error(credential)));
    expect(await claimStoryWithCredential('vc_abcdefgh', 2, credential)).toEqual({ ok: false, kind: 'unavailable' });
  });
});
