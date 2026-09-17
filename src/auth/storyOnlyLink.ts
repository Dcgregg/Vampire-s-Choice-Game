import { getSave } from '../sync/cloudClient';
import { claimStoryOnly } from '../sync/storyClaimClient';

export type StoryOnlyLinkOutcome =
  | { kind: 'claimed'; save: Awaited<ReturnType<typeof claimStoryOnly>> extends infer _T ? any : never }
  | { kind: 'no_anonymous_cloud_save' }
  | { kind: 'account_conflict'; reason?: string }
  | { kind: 'denied' | 'unauthenticated' | 'invalid_request' | 'unavailable' };

/**
 * Phase 6B opt-in coordinator. Deliberately NOT called by AuthContext yet.
 *
 * It first reads the anonymous cloud save so the claim is fenced to the exact
 * server revision the browser observed. It never derives a revision from local
 * storage and never sends account identity or reward fields to the claim route.
 */
export async function linkAnonymousStoryOnly(playerId: string): Promise<StoryOnlyLinkOutcome> {
  let anonymous;
  try {
    anonymous = await getSave(playerId);
  } catch {
    return { kind: 'unavailable' };
  }
  if (!anonymous) return { kind: 'no_anonymous_cloud_save' };

  const result = await claimStoryOnly(playerId, anonymous.revision);
  if (result.ok) return { kind: 'claimed', save: result.save };
  if (result.kind === 'conflict') return { kind: 'account_conflict', reason: result.reason };
  return { kind: result.kind };
}
