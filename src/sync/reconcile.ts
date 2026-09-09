/**
 * Pure sync decision logic (no network, no storage) so the revision/conflict
 * behaviour is deterministic and unit-testable.
 *
 * Documented matrix:
 *   local only            -> push_create      (create the cloud save)
 *   cloud only            -> adopt_cloud       (restore from cloud)
 *   both present          -> keep_local_push   (local-first; push, 409 resolves)
 *   nothing               -> noop
 *
 *   push, base == server  -> accept            (identical or local-newer)
 *   push, base != server  -> reject_adopt_server (cloud newer / stale client)
 *   push, no server yet   -> accept            (first create)
 */
export type StartAction = 'adopt_cloud' | 'keep_local_push' | 'push_create' | 'noop';

export function reconcileOnStart(params: {
  localHasPlayer: boolean;
  cloud: { revision: number } | null;
}): StartAction {
  const { localHasPlayer, cloud } = params;
  if (!cloud) return localHasPlayer ? 'push_create' : 'noop';
  if (!localHasPlayer) return 'adopt_cloud';
  return 'keep_local_push';
}

export type PushOutcome = 'accept' | 'reject_adopt_server';

export function resolvePushOutcome(baseRevision: number, serverRevision: number | null): PushOutcome {
  if (serverRevision === null) return 'accept';
  return baseRevision === serverRevision ? 'accept' : 'reject_adopt_server';
}
