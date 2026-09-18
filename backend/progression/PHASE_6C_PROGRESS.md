# Phase 6C player-ready progression — progress record

**Branch:** `phase-6c-player-ready-progression`  
**Base:** merged `main` commit `8671b001dfdb7dfff1ba2d2358df6986223bb6ea`  
**Status:** active implementation; not approved for merge, deployment, route registration or real-player migration.

## Binding product policy

- Preserve existing players' narrative progress.
- Do not import browser-derived BloodCoins or achievements into the trusted ledger.
- Authenticated account holders start with exactly **50 server-authoritative BloodCoins** and fresh achievements.
- Keep trusted progression inactive until the complete authenticated browser-to-API-to-disposable-Mongo flow is verified.

## Completed secure slice: authenticated ownership fencing

The server-derived account identity is now carried from trusted choice planning into the durable event reservation as `expectedOwnerType` and `expectedOwnerId`. Reservation lookup verifies that identity, retries cannot change it, and the transactional attributed ledger compare-and-set includes both fields. An ownership change that preserves the ledger revision and checkpoint can no longer receive the reserved award.

Coverage includes:

- pure tests proving the ledger CAS contains the authenticated owner;
- rejection of missing, anonymous or empty owner identity;
- retry rejection when the event ID is reused with a different owner;
- disposable-Mongo tests for ownership change before reservation and after reservation but before commit;
- all eight existing Phase 6B workflows now run on this Phase 6C branch as well as on pull requests to `main`.

## Verification completed locally

- production frontend build: passed;
- TypeScript check: passed;
- frontend tests: 120 passed;
- backend tests not requiring a separately running legacy API or disposable MongoDB: 300 passed before this slice;
- focused trusted-planner and reservation unit tests: 124 passed before the new owner-fence tests;
- disposable-Mongo ownership tests are delegated to GitHub Actions and must pass before this slice is considered complete.

## Remaining player-ready gates

1. Build the authenticated trusted-progression API orchestrator and strict public response contract.
2. Register routes only behind an explicit disabled-by-default feature flag.
3. Connect the client choice queue, retry/reconciliation and confirmed-versus-pending UI.
4. Implement existing-story preservation without converting legacy narrative flags into reward evidence.
5. Integrate the once-only 50-BloodCoin account opening grant and fresh achievements.
6. Define and implement terminal, lifecycle and achievement-awarding transitions.
7. Complete conflict, cancellation, account-switching, offline and second-device recovery UX.
8. Pass real-login browser-to-API-to-disposable-Mongo tests, full regression tests, security review and explicit cutover approval.

## Safety boundary

Do not merge, deploy, register experimental routes, write production ledgers, migrate player data or award real players from this branch without a separate verified release decision.
