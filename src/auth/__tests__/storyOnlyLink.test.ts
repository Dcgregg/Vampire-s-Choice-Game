import { afterEach, describe, expect, it, vi } from 'vitest';
import { getSave } from '../../sync/cloudClient';
import { claimStoryOnly } from '../../sync/storyClaimClient';
import { linkAnonymousStoryOnly } from '../storyOnlyLink';

vi.mock('../../sync/cloudClient', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../sync/cloudClient')>();
  return { ...actual, getSave: vi.fn() };
});
vi.mock('../../sync/storyClaimClient', () => ({ claimStoryOnly: vi.fn() }));

const getSaveMock = vi.mocked(getSave);
const claimMock = vi.mocked(claimStoryOnly);

afterEach(() => vi.clearAllMocks());

const anonymousSave = {
  playerId: 'vc_abcdefgh', saveSchemaVersion: 3, contentVersions: {},
  playerState: { progress: { currentSceneId: 'scene-two' }, bloodCoins: 9999 },
  revision: 7, createdAt: 'then', updatedAt: 'now',
};

describe('linkAnonymousStoryOnly', () => {
  it('fences the claim to the exact anonymous cloud revision it just observed', async () => {
    getSaveMock.mockResolvedValue(anonymousSave);
    claimMock.mockResolvedValue({ ok: true, save: { ...anonymousSave, playerState: { ...anonymousSave.playerState, bloodCoins: 0 }, revision: 1 } });

    const result = await linkAnonymousStoryOnly('vc_abcdefgh');

    expect(claimMock).toHaveBeenCalledWith('vc_abcdefgh', 7);
    expect(result.kind).toBe('claimed');
  });

  it('does not attempt a claim when there is no anonymous cloud save', async () => {
    getSaveMock.mockResolvedValue(null);
    expect(await linkAnonymousStoryOnly('vc_abcdefgh')).toEqual({ kind: 'no_anonymous_cloud_save' });
    expect(claimMock).not.toHaveBeenCalled();
  });

  it('preserves an account conflict as a decision point instead of choosing a save', async () => {
    getSaveMock.mockResolvedValue(anonymousSave);
    claimMock.mockResolvedValue({ ok: false, kind: 'conflict', resolution: 'review_existing_progress_or_retry', reason: 'account already has a save' });
    expect(await linkAnonymousStoryOnly('vc_abcdefgh')).toEqual({ kind: 'account_conflict', reason: 'account already has a save' });
  });

  it('does not claim from stale local metadata when anonymous cloud lookup fails', async () => {
    getSaveMock.mockRejectedValue(new Error('offline'));
    expect(await linkAnonymousStoryOnly('vc_abcdefgh')).toEqual({ kind: 'unavailable' });
    expect(claimMock).not.toHaveBeenCalled();
  });
});
