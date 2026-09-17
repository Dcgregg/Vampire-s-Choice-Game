# Phase 6B recovery sweep: failure policy (inert)

This document describes the current behavior of `sweep_expired` and the operational decisions required **before** any scheduler or live route is enabled. It does not authorize activation.

## Current behavior

- The sweep selects at most `limit` expired `committing` events in deterministic lease-expiry and ID order. It never deletes unresolved events.
- `ReservationBusy`, `ProgressionConflict`, and `ReservationInvariantError` from an individual recovery attempt are counted separately; the sweep continues to the next event. A non-`applied` return raises `ReservationInvariantError`.
- Any other exception, including an unexpected database or connectivity failure, **propagates and aborts the current sweep**. The caller receives no partial `SweepResult`; already completed operations are not rolled back. Unprocessed events remain eligible for a later run. Do not interpret a failed sweep as zero work or blindly repeat side effects: reconcile durable event and ledger state first.
- The adapter's transactional `commit` deliberately does not silently retry ambiguous transaction failures. A trusted operator or future worker must reconcile the event and ledger before retrying.

## Recovery adapter boundary (review finding)

`sweep_expired(store)` accepts any store exposing `events` and `recover`; it does **not** enforce the attribution-aware adapter. `backend/tests/test_recovery_sweep_integration.py` currently exercises `MongoReservationStore`, whose revision-only recovery/finalisation inference is not safe for trusted awards when a foreign writer advances a ledger. Those tests establish the sweep's batching and lease behavior, **not** the attribution invariant. A future trusted recovery worker must instantiate `AttributedMongoReservationStore` only, enforce exclusive trusted ledger writes, and prove event-to-ledger attribution before marking an event applied. Add dedicated disposable-MongoDB sweep tests with the attributed store for foreign same/higher-revision writes, later legitimate events, expired lease races and ambiguous commit outcomes before wiring a scheduler. Do not run the older adapter against authoritative ledgers.

## Pre-activation decisions and checks

1. Define the scheduler's error reporting, alerting, backoff and retry policy for an aborted sweep; do not swallow exceptions or mark the batch successful.
2. Confirm unique indexes, durable writes, and a transaction-capable MongoDB replica set in the intended environment; keep the attributed adapter the sole progression-revision writer.
3. Review recovery behavior for transient connectivity loss, ambiguous commit outcomes, stale lease ownership, and repeated failures; retain unresolved events for investigation.
4. Separately review and authorize trusted event validation, authentication/ownership checks, endpoint wiring, deployment, and any production migration. The current branch does not make client-derived coins or achievements authoritative.

Regression coverage: `backend/tests/test_recovery_sweep_failure_policy.py`, included in the isolated Phase 6B workflow. Existing integration coverage lives in `backend/tests/test_recovery_sweep_integration.py` and currently uses the older adapter; it is not attributed-sweep acceptance coverage.
