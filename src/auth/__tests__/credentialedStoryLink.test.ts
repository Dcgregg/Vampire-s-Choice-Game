import { afterEach, describe, expect, it, vi } from 'vitest';
import { linkFreshCredentialedStory } from '../credentialedStoryLink';

const credential = 'A'.repeat(43);
const issuedSave = {
  playerId: 'vc_abcdefgh', saveSchemaVersion: 3, contentVersions: {},
  playerState: { progress: {}, bloodCoins: 999 }, revision: 1,
  createdAt: 'now', updatedAt: 'now',
};
const accountSave = {
  saveSchemaVersion: 3, contentVersions: {}, playerState: { progress: {}, bloodCoins: 0 },
  revision: 1, createdAt: 'now', updatedAt: 'now',
};
const response = (status: number, body: unknown) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json' },
});
afterEach(() => vi.unstubAllGlobals());

describe('linkFreshCredentialedStory', () => {
  it('claims only the issued ID and exact server revision with proof in a header', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(200, accountSave));
    vi.stubGlobal('fetch', fetchMock);
    expect(await linkFreshCredentialedStory(issuedSave, credential)).toEqual({
      kind: 'claimed', save: accountSave,
    });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).not.toContain(credential);
    expect(init.headers['X-Anonymous-Claim-Credential']).toBe(credential);
    expect(JSON.parse(init.body)).toEqual({ playerId: issuedSave.playerId, expectedAnonymousRevision: 1 });
    expect(init.body).not.toContain('bloodCoins');
  });

  it('does not import either save on an account conflict', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(409, {
      detail: { error: 'claim_conflict', accountSave, anonymousSave: issuedSave },
    })));
    expect(await linkFreshCredentialedStory(issuedSave, credential)).toEqual({ kind: 'account_conflict' });
  });

  it('does not claim with an invalid revision or missing credential', async () => {
    const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
    expect(await linkFreshCredentialedStory({ ...issuedSave, revision: 0 }, credential))
      .toEqual({ kind: 'invalid_request' });
    expect(await linkFreshCredentialedStory(issuedSave, ''))
      .toEqual({ kind: 'invalid_request' });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('leaves account mode unchanged on network failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    expect(await linkFreshCredentialedStory(issuedSave, credential))
      .toEqual({ kind: 'unavailable' });
  });
});
