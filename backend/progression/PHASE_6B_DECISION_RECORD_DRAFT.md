# Phase 6B decision record — four design gates (PROPOSED, INERT)

> Historical proposal. See `PHASE_6C_COMPLETION_REVIEW.md` for the implemented
> decisions; activation, merge and deployment still require explicit approval.

**Status:** review draft, not approved policy or implemented behaviour. No ledger creation, import, route, worker, schema migration, production write, merge or deployment is authorized by this record. The four decisions below must be explicitly accepted or amended before implementation. Companion documents: `TRUSTED_API_CONTRACT_DRAFT.md`, `TRUSTED_API_ACCEPTANCE_MATRIX.md`, `TRUSTED_STATE_MACHINE_REVIEW.md`.

## 1. Ledger creation and legacy provenance

**Existing:** `reducer.new_state(registry)` returns zero coins, initial affinity, empty flags and no achievements; it deliberately does not apply an opening grant. Account and anonymous cloud saves are client-controlled, not trusted progression records. The reservation adapter already recognizes `openingGranted` and `lifecycleApplied` as optional projection fields but does not initialize or validate them.

**Proposal for approval:** limit the first trusted ledger to a server-authenticated account owner; create at most one ledger per account through a separate, idempotent, server-owned initialization transaction. Initialize from the trusted registry, not from `account_saves.playerState` or an anonymous `playerId`. Proposed initial durable state: `ownerType='account'`, server-derived `ownerId`, `progressionRevision=0`, `coins.confirmed=0`, `achievements={}`, `derived=new_state(registry)`, `checkpoint={bookId:<approved opening book>,currentSceneId:<approved opening scene>,terminal:false}`, `openingGranted=false`, `lifecycleApplied=[]`, and the content pin specified in decision 2. Do not assume the opening book/scene IDs until verified against exported content. Ledger ID and creation timestamp are server-generated; do not accept client-supplied ledger fields. Concurrent initializers must return the same durable ledger without a second grant or revision.

**Legacy policy proposal:** do not import historical coins or achievements into this first release. Preserve old saves separately for reading/continuity; any future import needs its own reviewed provenance, abuse controls, reconciliation and tests. `PublicLedgerAchievement.source='imported'` exists in the current contract, but its existence is not authorization to import. A missing ledger must not be silently created by an event retry or by reading a cloud save.

**Tests to add after approval:** duplicate/concurrent initialization yields one ledger; spoofed owner and edited saves do not affect its seed; absent trusted content fails without a partial ledger; repeated reads do not grant coins; creation cannot run on anonymous player-ID proof alone.

## 2. Durable trusted-content pin

**Existing:** `trusted_content.book_entry(registry, bookId, version)` checks that a requested version exists in the server registry. The pure choice guard does not prove that the server-loaded ledger is pinned to that version; the existing `PublicLedgerCheckpoint` exposes `bookId` and `currentSceneId`, not a version.

**Proposal for approval:** add a required server-owned `checkpoint.contentVersion` (strict positive integer) to the **durable** checkpoint and validate `(checkpoint.bookId, checkpoint.contentVersion, checkpoint.currentSceneId)` against trusted exported content when initializing and processing a *new* event. Require `event.bookId == checkpoint.bookId` and `event.contentVersion == checkpoint.contentVersion` for ordinary choices; do not let the browser select a newer version. The version remains immutable for a book until an explicitly defined, atomic transition changes book and version together. Do not infer a pin from a registry lookup alone or automatically upgrade a ledger when the registry changes. Retain the pinned content artifact for active ledgers, or fail closed if unavailable. The public response may expose the pinned version after the wire contract is reviewed; do not modify the current public model by implication.

**Compatibility gate:** the current reservation adapter compares full expected checkpoints and its projection whitelist includes `checkpoint`; tests and any eventual full-ledger validator must be updated together for the new required field. Existing test fixtures without a version are not evidence that a version is already stored. No backfill or migration is approved here.

**Tests to add after approval:** valid registry version that differs from durable pin is rejected for a new event; unknown/missing pin and missing pinned artifact fail closed; a duplicate applied under an older pin is resolved by its durable event record before *current-state* version/checkpoint checks; a concurrent transition cannot commit an event against the old checkpoint.

## 3. Event identity, canonical payload and retry semantics

**Existing:** `MongoReservationStore` has a unique `(ledgerId,eventId)` index and stores a `payloadHash`; it is inert and relies on a trusted caller. The API contract requires authentication, strict parsing and duplicate resolution before new-event revision/checkpoint checks. Exact canonical encoding, rejection persistence and response envelope remain undecided.

**Proposal for approval:** scope event IDs to the server-resolved ledger, not to a client-supplied owner or global player ID. Require a bounded nonempty event ID with an explicitly chosen format and length before implementation. Hash a deterministic UTF-8 canonical serialization of **all validated event fields** (including kind, eventId, bookId, contentVersion, baseProgressionRevision and kind-specific fields), with fixed key ordering and unambiguous integer/string encoding; reject extra fields and bool-as-int before hashing. Pin an exact canonicalization algorithm and fixtures across languages before wiring the caller. The event ID and digest must not include client-supplied rewards or projections because those fields are forbidden.

**Processing order proposal:** authenticate and identify the ledger; strictly parse/canonicalize; look up `(ledgerId,eventId)` and compare digest; return the durable outcome for an identical confirmed event even if its original revision, scene or version is no longer current; reject changed payload under the same ID; reconcile a reserved/in-flight event without assuming success. Only an unclaimed new event is checked against the current ledger pin, revision, checkpoint and eligibility, then reduced and transactionally reserved/committed. Keep a durable record of claimed IDs; never recycle an ID after a committed rejection. Whether to persist pre-reservation validation rejections, and their exact status/error envelope, **requires an explicit choice**. An ambiguous commit is indeterminate until durable reconciliation; no second award and no fabricated confirmation.

**Tests to add after approval:** byte-stable cross-language canonical fixtures; duplicate after checkpoint/version advancement; payload collision; malformed/oversize input before any write; concurrent same-ID retries; distinct events racing at one revision; failed/ambiguous commit reconciliation; rejected-ID reuse under the chosen rejection policy.

## 4. Opening, achievements, lifecycle and book transitions

**Existing:** `apply_lifecycle` only checks whether a lifecycle ID exists and may unlock its achievement; it does not prove eligibility. `apply_choice` can award direct/affinity achievements and returns `nextSceneId` and `endsBook`. The pure guard intentionally rejects achievement-awarding and terminal choices. The adapter can store `lifecycleApplied` and `openingGranted`, but does not define their meaning. The current achievement public metadata has `unlockedAt` and `source`.

**Proposed conservative staged rules, each requiring approval:**

- **Opening grant:** do not grant during a ledger read or implicit creation. Define the amount and eligibility from trusted exported rules, then award exactly once through a dedicated server-authorized transition that atomically sets `openingGranted=true`, changes confirmed and derived coins together, and consumes one progression revision. Until the amount, event identity and eligibility are pinned, leave opening grants disabled.
- **Lifecycle:** enumerate the actual exported lifecycle IDs and specify a durable predicate for each (for example, a verified book-start or book-complete checkpoint). Store an applied marker scoped to the appropriate book/version/lifecycle identity and also deduplicate by event ID. Registry membership alone is never sufficient. Do not enable lifecycle processing before these predicates and replay semantics are tested.
- **Achievements:** for each award, atomically update the derived achievement list and durable achievement metadata (`unlockedAt` timestamp and `source='awarded'` for server-derived awards); define timestamp source and any provenance fields before coding. No duplicate unlock or partial award. Until metadata is specified, keep achievement-bearing choices rejected by the pure guard.
- **Terminal/sequel:** define a distinct, authorized transition for finishing a book and selecting the next book/version/opening scene. A normal choice cannot run from a terminal checkpoint. Do not infer next-book entry from `endsBook` or `nextSceneId`; no automatic sequel or replay policy is approved. Keep terminal choices rejected until the transition contract is explicit.

**Tests to add after approval:** opening grant once under retries/concurrency; ineligible lifecycle and replay rejected; direct and affinity-derived awards update both stores atomically; terminal choice cannot accidentally start another book; version pin changes only in an authorized atomic book transition; ambiguous commits never double-award.

## Approval checklist and implementation boundary

Please explicitly approve or amend: (1) clean account-only initialization with no legacy import and a verified opening checkpoint; (2) durable checkpoint content-version pin and artifact retention; (3) ledger-scoped event IDs, canonical encoding, and rejection persistence; (4) opening amount/eligibility, lifecycle predicates, achievement metadata and terminal/sequel rules. The specific ID bounds, canonical format, exported lifecycle IDs, opening amount, opening scene, response codes, CSRF posture and deployment requirements are **not** resolved by this draft.

Only after those choices: write pure validation tests, implement a trusted caller against fake stores, then disposable-Mongo concurrency tests. Separately review any route registration, initialization rollout, migration, merge or deployment. Existing green CI does not certify these unimplemented cases.
