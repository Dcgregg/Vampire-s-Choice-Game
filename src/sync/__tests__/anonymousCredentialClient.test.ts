import { afterEach, describe, expect, it, vi } from 'vitest';
import { issueAnonymousCredential } from '../anonymousCredentialClient';

const credential = 'A'.repeat(43);
const save = { playerId: 'vc_abcdefgh', saveSchemaVersion: 3, contentVersions: {},
  playerState: { progress: {} }, revision: 1, createdAt: 'now', updatedAt: 'now' };
const response = (status: number, body: unknown) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json' },
});
afterEach(() => vi.unstubAllGlobals());

describe('issueAnonymousCredential', () => {
  it('creates a fresh server identity without supplying an ID or state', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(201, { save, claimCredential: credential }));
    vi.stubGlobal('fetch', fetchMock);
    expect(await issueAnonymousCredential()).toEqual({ ok: true, save, claimCredential: credential });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain('/anonymous/credentialed-save');
    expect(url).not.toContain(credential);
    expect(init.method).toBe('POST');
    expect(init.credentials).toBe('omit');
    expect(init.cache).toBe('no-store');
    expect(init.body).toBe('{}');
  });

  it.each([
    null, {}, { save, claimCredential: '' },
    { save: { ...save, playerId: 'legacy-id' }, claimCredential: credential },
    { save: { ...save, claimCredentialDigest: 'private' }, claimCredential: credential },
    { save: { ...save, revision: 0 }, claimCredential: credential },
    { save: { ...save, contentVersions: { book1: -1 } }, claimCredential: credential },
  ])('rejects malformed successful issuance without adopting an identity', async body => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(201, body)));
    expect(await issueAnonymousCredential()).toEqual({ ok: false, kind: 'invalid_response' });
  });

  it('does not expose proof in errors or treat a non-201 response as issuance', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(200, { save, claimCredential: credential })));
    expect(await issueAnonymousCredential()).toEqual({ ok: false, kind: 'unavailable' });
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error(credential)));
    expect(await issueAnonymousCredential()).toEqual({ ok: false, kind: 'unavailable' });
  });
});
