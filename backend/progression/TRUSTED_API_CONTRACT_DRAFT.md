# Phase 6B trusted progression API contract — design draft (INERT)

**Status:** proposal for review, not an implemented endpoint or authorization to activate. No route, scheduler, database migration, or production credential is introduced by this document.

## Existing boundaries

- `backend/progression/contracts.py` defines `ChoiceProgressionEvent`, `LifecycleProgressionEvent`, `EventResult`, and `PublicLedger`; it is not imported by `server.py`.
- `backend/progression/reducer.py` derives choice and lifecycle effects from versioned trusted content. It does not persist, deduplicate, authenticate, or enforce ledger concurrency.
- `backend/progression/mongo_reservations.py` implements an inert reservation/commit adapter. Its transactional guarantees depend on unique indexes, exclusive progression-revision ownership, and a transaction-capable MongoDB deployment.
- `backend/server.py` currently exposes anonymous and authenticated cloud-save routes. Those saves contain client-supplied `playerState`, including `bloodCoins` and `achievements`, and must not be treated as an authoritative ledger.

## Proposed interface (NOT registered)

`POST /api/me/progression/events` is a **candidate path**, not an existing route. Require an authenticated session resolved server-side with `_current_user`; derive owner identity from `user_id`, never from a body-supplied player ID, ledger ID, owner type, coins, achievements, projection, or awards. Anonymous trusted progression is **out of scope until a separately reviewed ownership mechanism exists**. The existing anonymous cloud-save player ID alone is not proof of ownership.

Accept one discriminated event matching the existing `ChoiceProgressionEvent` or `LifecycleProgressionEvent` fields:

- Shared: `kind`, `eventId`, `bookId`, `contentVersion`, `baseProgressionRevision`.
- Choice: `fromSceneId`, `choiceId`.
- Lifecycle: `lifecycleId`.

Reject unknown fields at the trust boundary; impose explicit length, type, and size bounds before hashing. The client must not submit an award amount, target revision, next scene, achievement unlock, or final ledger state. Canonicalize the validated event and bind `(owner, eventId)` to its payload digest; the same ID with a different payload is a conflict, not a second action. Choose and document the exact event-ID scope and canonical serialization before implementation.

## Proposed processing order

1. Authenticate, derive account ownership, and load an account-owned trusted ledger. Do not use the client-controlled `account_saves.playerState` as an authoritative starting projection. Missing-ledger initialization and any import from legacy saves require a separate, explicitly approved policy.
2. Strictly parse the event's shape, bounded fields, and canonical payload for deduplication. This is **not** current-state eligibility validation: do not yet reject a previously applied event merely because its historical base revision, source checkpoint, or content version differs from today's ledger state. The exact event-ID scope, canonical encoding, and treatment of previously rejected events still require approval.
3. Resolve a previously recorded `(owner, eventId)` against its durable canonical payload **before** checking the new-event base revision or current checkpoint: return the durable applied result for an identical payload; reject a payload mismatch; reconcile an in-flight reservation without double-awarding. A previously rejected event must not become a new award by reusing its ID. Do not infer success from an unresolved reservation.
4. Only for an unclaimed **new** event, validate its content version against the ledger's durable trusted-content pin, check choice reachability from the current checkpoint, and enforce separately documented lifecycle eligibility. Registry existence alone does not prove the ledger is pinned to that version or that an event is reachable or eligible. Require `baseProgressionRevision` to match the authoritative ledger revision. Derive effects and the next projection server-side with the trusted reducer; never trust the browser's coin balance, achievements, flags, affinities, or next checkpoint.
5. Reserve and commit through the transaction-backed adapter with its conditional revision/checkpoint guards. Persist the event outcome and ledger mutation atomically; do not introduce a second progression-revision writer. On an ambiguous transaction failure, report an indeterminate/retryable outcome without claiming success and reconcile durable state before a retry.
6. Return only a server-derived public ledger and event result. Do not expose Mongo IDs, session tokens, internal lease ownership, or mutable reservation details.

## Proposed response semantics (to pin with tests)

- Applied new event: `200` with `EventResult(status="confirmed")` and the authoritative `PublicLedger`.
- Identical already-applied event: `200` with `EventResult(status="duplicate")` and the durable authoritative ledger; no new revision or award.
- Malformed/unknown content or ineligible event: `422` with a stable machine-readable reason; decide whether to durably record a rejected event before implementation.
- Stale base revision, wrong checkpoint, or reused event ID with different payload: `409` with a stable reason and no award. Avoid disclosing another owner's ledger.
- No/expired authentication: `401`. A missing or non-owned ledger must not reveal whether another user's ledger exists.
- Infrastructure or ambiguous commit failure: non-success response with a stable retryable/indeterminate reason, never a fabricated confirmation. Exact status and safe retry instructions remain an explicit design decision.

These codes are **proposed**, not current behavior. Existing `EventResult` permits `confirmed`, `duplicate`, and `rejected`; the eventual envelope and error schema need review before coding.

## Pre-implementation acceptance tests

- Unauthenticated request, another user's ledger ID, and anonymous player-ID spoofing cannot award or read account progression.
- Browser-supplied coins, achievements, projection, and extra fields cannot influence awards; invalid content versions, unreachable choices, and ineligible lifecycle events fail closed for **new** events.
- Exact duplicate returns the same durable result without increment, even when its original base revision is now stale or its source scene is no longer current; same event ID with changed payload conflicts.
- Concurrent distinct events at one base revision cannot both advance the ledger; stale checkpoint, stale lease owner, and ambiguous transaction outcomes do not double-award.
- Legacy cloud-save edits and claims cannot mutate the trusted ledger or bypass its revision owner; migration/import policy is separately tested and approved.
- Errors never claim success before durable commit; recovery and observability follow `RECOVERY_FAILURE_POLICY.md`.

## Decisions required before any route is wired

1. Account-ledger creation and treatment of existing anonymous/account saves, including whether any historical coins/achievements may be imported and how their provenance is labelled.
2. Lifecycle eligibility and book-transition rules; the current reducer checks that a lifecycle ID exists but does not itself prove the event is eligible.
3. Event ID namespace, payload canonicalization, durable rejection semantics, exact response envelope, and retry/error codes.
4. Authentication/session CSRF posture for cookie-based writes, rate limits, abuse controls, and safe ledger-read authorization.
5. Deployment-specific indexes, transaction support, rollout/migration plan, monitoring, reconciliation, and explicit activation authorization.

Until these decisions are made, keep all trusted progression code inert and keep the existing cloud-save trust model clearly separate.
