# Phase 6B recovery sweep: failure policy (inert)

This document describes the current behavior of `sweep_expired` and the operational decisions required **before** any scheduler or live route is enabled. It does not authorize activation.

## Current behavior

- The sweep selects at most `limit` expired `committing` events in deterministic lease-expiry and ID order. It never deletes unresolved events.
- `ReservationBusy`, `ProgressionConflict`, and `ReservationInvariantError` from an individual recovery attempt are counted separately; the sweep continues to the next event. A non-`applied` return raises `ReservationInvariantError`.
- Any other exception, including an unexpected database or connectivity failure, **propagates and aborts the current sweep**. The caller receives no partial `SweepResult`; already completed operations are not rolled back. Unprocessed events remain eligible for a later run. Do not interpret a failed sweep as zero work or blindly repeat side effects: reconcile durable event and ledger state first.
- The adapter's transactional `commit` deliberately does not silently retry ambiguous transaction failures. A trusted operator or future worker must reconcile the event and ledger before retrying.

## Pre-activation decisions and checks

1. Define the scheduler's error reporting, alerting, backoff and retry policy for an aborted sweep; do not swallow exceptions or mark the batch successful.
2. Confirm unique indexes, durable writes, and a transaction-capable MongoDB replica set in the intended environment; keep the adapter the sole progression-revision writer.
3. Review recovery behavior for transient connectivity loss, ambiguous commit outcomes, stale lease ownership, and repeated failures; retain unresolved events for investigation.
4. Separately review and authorize trusted event validation, authentication/ownership checks, endpoint wiring, deployment, and any production migration. The current branch does not make client-derived coins or achievements authoritative.

Regression coverage: `backend/tests/test_recovery_sweep_failure_policy.py`, included in the isolated Phase 6B workflow. Existing integration coverage lives in `backend/tests/test_recovery_sweep_integration.py`.
