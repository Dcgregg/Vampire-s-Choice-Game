import { afterEach, describe, expect, it, vi } from 'vitest';
import { claimStoryOnly } from '../storyClaimClient';

const jsonResponse = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

afterEach(() => vi.unstubAllGlobals());

describe('claimStoryOnly', () => {
  it('sends only player id and exact anonymous revision with credentials', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {
      saveSchemaVersion: 3, contentVersions: {}, playerState: { bloodCoins: 0 }, revision: 1,
      createdAt: 'now', updatedAt: 'now',
    }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await claimStoryOnly('vc_abcdefgh', 7);

    expect(result.ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0];
    expect(init.credentials).toBe('include');
    expect(JSON.parse(init.body)).toEqual({ playerId: 'vc_abcdefgh', expectedAnonymousRevision: 7 });
    expect(JSON.parse(init.body)).not.toHaveProperty('userId');
  });

  it('does not treat an account conflict as success or import either save', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(409, {
      detail: {
        error: 'claim_conflict',
        reason: 'account already has a save; explicit choice required',
        resolution: 'review_existing_progress_or_retry',
      },
    })));

    expect(await claimStoryOnly('vc_abcdefgh', 2)).toEqual({
      ok: false,
      kind: 'conflict',
      resolution: 'review_existing_progress_or_retry',
      reason: 'account already has a save; explicit choice required',
    });
  });

  it.each([
    [401, 'unauthenticated'],
    [403, 'denied'],
    [422, 'invalid_request'],
  ] as const)('maps HTTP %s to %s', async (status, kind) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(status, { detail: { error: kind } })));
    expect(await claimStoryOnly('vc_abcdefgh', 2)).toEqual({ ok: false, kind });
  });

  it('keeps the game recoverable when the endpoint is unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    expect(await claimStoryOnly('vc_abcdefgh', 2)).toEqual({ ok: false, kind: 'unavailable' });
  });
});
