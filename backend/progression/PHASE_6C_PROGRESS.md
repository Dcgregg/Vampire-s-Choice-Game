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

## Completed secure slice: strict authenticated route contract

- Added a server-owned choice orchestrator that loads ledgers only by the authenticated account identity, handles durable duplicate/recovery paths before new-event validation, and never accepts client projections or rewards.
- Added an opt-in `POST /api/me/progression/choices` router factory with strict input, stable conflict/validation/indeterminate errors and no-store responses.
- The router is deliberately not imported or registered by `server.py`; live behaviour remains unchanged.
- First-account ledger creation and the 50-BloodCoin grant remain a separate activation slice, so a missing trusted ledger fails closed.

## Completed secure slice: account bootstrap and legacy-story separation

- Added an authenticated, idempotent account bootstrap service and an opt-in `POST /api/me/progression/bootstrap` route factory with no client-supplied state.
- New account ledgers start with exactly 50 confirmed BloodCoins, fresh achievements and a server-owned opening checkpoint.
- Fixed the opening grant to update confirmed and reducer-derived coin balances together; the first trusted choice can now plan from 50 to 60 without failing the consistency guard.
- Existing progressed ledgers are returned without a top-up. Existing unawarded, malformed or wrong-value revision-zero ledgers fail closed and require an explicit reviewed migration.
- Disposable-Mongo coverage proves that credential-protected legacy story claiming preserves narrative progress while stripping client rewards, and that later tampering with compatibility save rewards cannot change the trusted ledger.
- The bootstrap and story-claim routes remain unregistered; live players and production data are unchanged.

## Completed secure slice: authenticated choice service recovery coverage

- Added disposable-Mongo end-to-end coverage through the authenticated choice service, durable reservation adapter and transaction-backed ledger.
- Identical retries return the authoritative ledger without applying the award twice, while a reused event ID with changed intent fails closed.
- Concurrent identical requests can apply only once; concurrent different events can reserve the next ledger revision only once.
- A retry after a commit-before-finalisation crash reconciles from durable attribution, and an active unknown outcome remains indeterminate until its lease safely expires.
- This coverage does not register the experimental route or enable trusted progression for live players.

## Verification completed locally

- production frontend build: passed;
- TypeScript check: passed;
- frontend tests: 120 passed;
- backend tests not requiring a separately running legacy API or disposable MongoDB: 335 passed, 119 service-dependent tests skipped locally;
- all eight GitHub Actions workflows passed for both push and pull-request triggers after adding the authenticated choice-service duplicate, concurrency and recovery coverage;
- disposable-Mongo ownership, opening-grant, story-separation and trusted-choice service tests passed without production credentials.

## Remaining player-ready gates

1. Register routes only behind an explicit disabled-by-default feature flag.
2. Connect the client choice queue, retry/reconciliation and confirmed-versus-pending UI.
3. Define and implement terminal, lifecycle and achievement-awarding transitions.
4. Complete conflict, cancellation, account-switching, offline and second-device recovery UX.
5. Pass real-login browser-to-API-to-disposable-Mongo tests, full regression tests, security review and explicit cutover approval.

## Safety boundary

Do not merge, deploy, register experimental routes, write production ledgers, migrate player data or award real players from this branch without a separate verified release decision.
