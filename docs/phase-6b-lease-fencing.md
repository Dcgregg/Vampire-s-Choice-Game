# Phase 6B — strict lease fencing (design gate, not implemented)

Status: **blocked for live use**. This is a design and test plan, not a claim that the current adapter is fenced. Keep `phase-6b-trusted-progression` isolated; do not enable routes, schedule recovery, merge to `main`, or use a production database.

## Observed behavior

`MongoReservationStore.commit()` reads a `committing` event with a matching `leaseOwner` and unexpired `leaseUntil`, then separately executes the ledger CAS. `acquire()` can change `leaseOwner` between those operations. `backend/tests/test_mongo_reservations_lease_interleaving.py` deliberately forces this sequence and currently demonstrates that the former owner can still perform the ledger write. The unique `(ledgerId, targetRevision)` reservation and ledger revision CAS prevent a second increment in that test, but **do not fence the former owner**. The 45-test CI pass is a regression baseline, not proof of strict fencing.

## Required invariant

A ledger CAS must not commit if a competing worker has acquired the event lease before that CAS commits. The event's lease ownership check and ledger mutation must share an atomic concurrency boundary. A second preflight read, an application-level lock, or a post-write lease check is insufficient.

## Proposed implementation (requires verification)

1. Use a MongoDB replica set (or supported sharded deployment) and a Motor client session with a multi-document transaction. A standalone `mongo:7` service cannot run these transactions; change only the **disposable CI service** to a single-node replica set, initialize it, and verify transaction support before introducing the new commit path.
2. Within one transaction, conditionally **write** the reservation event using `_id`, `status=committing`, `leaseOwner`, and `leaseUntil > now`; for example increment an internal `commitFence` counter. A read-only event check is not enough: the event write must conflict with a concurrent `acquire()` update to that same event document. Use the persisted `nextProjection` and `expectedCheckpoint` from that transaction's event, never a caller-supplied replacement.
3. In the same transaction, perform the existing guarded ledger CAS (`progressionRevision`, checkpoint, and owner/merge fences). Abort on missing event, changed owner, expired lease, invalid projection, or checkpoint conflict. Commit the transaction only when the guarded write succeeds, or when an explicitly proven already-applied idempotent path is reached.
4. Preserve unique event/revision indexes and immutable reserved projection. Keep crash recovery and finalisation idempotent; explicitly handle transaction write conflicts, transient transaction errors, unknown commit outcomes, and lease expiry without recomputing awards or claiming success from an ambiguous result. A retry must re-read durable event/ledger state and respect the original event ID.
5. Ensure `acquire()` and every other ownership-changing path writes the same event document, and that **all** ledger revision writers use the same protocol. Validate durability/write concern and transaction behavior on the actual deployment topology before any live use.

## Acceptance tests before implementation is considered complete

- Deterministically pause the old worker after its transactional event check/write; have the competing worker attempt lease takeover, then resume the old worker. Assert that either the old transaction commits first and takeover/recovery observes its result, **or** takeover commits first and the old transaction aborts. Never accept an old-owner ledger write after a completed takeover.
- Exercise takeover before the transaction, during the transaction, and after an ambiguous transaction commit. Assert one target reservation, one revision increment, one immutable projection, and correct finalisation/recovery.
- Test simultaneous workers, process crash after transaction commit but before finalisation, later revisions, invalid/legacy projection, claimed or merged ledger, and retries under transient write conflicts.
- Run the full Phase 6B suite against a disposable replica-set MongoDB in CI. The current standalone CI pass cannot validate a transaction-based solution.

Do not modify `backend/server.py`, expose an endpoint, schedule the sweep, or connect production credentials as part of this design gate.
