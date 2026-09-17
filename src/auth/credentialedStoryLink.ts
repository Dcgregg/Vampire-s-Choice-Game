import type { CloudSave } from '../sync/cloudClient';
import { claimStoryWithCredential } from '../sync/credentialedStoryClaimClient';
import type { StoryAccountSave } from '../sync/storyClaimClient';

export type CredentialedStoryLinkOutcome =
  | { kind: 'claimed'; save: StoryAccountSave }
  | { kind: 'account_conflict' }
  | { kind: 'denied' | 'unauthenticated' | 'invalid_request' | 'unavailable' };

/**
 * Opt-in coordinator for a freshly issued credential and its matching server
 * save. It does not read legacy anonymous saves, adopt local state, persist the
 * bearer secret, or switch account mode. Never call automatically on login.
 * The caller must preserve its anonymous state on every unsuccessful outcome.
 */
export async function linkFreshCredentialedStory(
  issuedSave: CloudSave, claimCredential: string,
): Promise<CredentialedStoryLinkOutcome> {
  if (!issuedSave || typeof issuedSave.playerId !== 'string' ||
      !Number.isSafeInteger(issuedSave.revision) || issuedSave.revision < 1) {
    return { kind: 'invalid_request' };
  }
  const result = await claimStoryWithCredential(
    issuedSave.playerId, issuedSave.revision, claimCredential,
  );
  if (result.ok) return { kind: 'claimed', save: result.save };
  if (result.kind === 'conflict') return { kind: 'account_conflict' };
  return { kind: result.kind };
}
