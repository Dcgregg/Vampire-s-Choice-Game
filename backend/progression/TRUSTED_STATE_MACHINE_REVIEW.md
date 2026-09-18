# Phase 6B trusted state-machine review (INERT)

> Historical Phase 6B review. The implemented Phase 6C decisions and current
> cutover boundary are recorded in `PHASE_6C_COMPLETION_REVIEW.md`.

**Status:** an isolated, pure, nonterminal choice guard is implemented and tested; this is **not** approval to initialize ledgers, register an endpoint, schedule recovery, migrate saves, merge into `main`, or deploy. Read alongside `TRUSTED_API_CONTRACT_DRAFT.md`, `TRUSTED_API_ACCEPTANCE_MATRIX.md`, and `PHASE_6B_DECISION_RECORD_DRAFT.md`.

## Observed implementation boundary

- `strict_event_input.py` validates the event's shape, required revision, types, and provisional string limits. It does **not** validate authentication, content, checkpoint reachability, or lifecycle eligibility.
- `trusted_content.book_entry` checks a `(bookId, contentVersion)` against the trusted registry; `reducer.apply_choice` checks that the named scene and choice exist and derives awards and `nextSceneId`/`endsBook`. The reducer does **not** compare the source scene to a durable checkpoint.
- `choice_checkpoint_guard.prepare_nonterminal_choice` is a **pure proposal builder**, not an event processor or authorization boundary. It checks a server-loaded ledger's revision, book/source checkpoint, strict positive-integer `checkpoint.contentVersion` against the event version, nonterminal state, merge/fence/claim markers, confirmed-versus-derived coin consistency, and agreement between the recorded achievement IDs and the derived achievement list (including rejection of duplicate derived IDs). It looks up content using the durable version pin, derives on a copy, rejects terminal and achievement-awarding choices, verifies the next scene exists, and returns an expected checkpoint and proposed projection preserving that pin. Its tests run in the isolated Phase 6B workflow. These checks are **not** full ledger-schema or achievement-metadata validation. The guard does not fetch or authenticate a ledger, resolve duplicate events, establish that the supplied ledger was loaded from an authoritative store, reserve/commit an event, or define lifecycle or terminal transitions. Its caller must do the missing work before any trusted write.
- `reducer.apply_lifecycle` checks only that a lifecycle ID exists and unlocks its achievement when present. Existence alone is not permission to award.
- `MongoReservationStore.reserve` can accept caller-supplied projection and awards. Its caller must be trusted and must validate against a durable ledger; the adapter is not an eligibility validator. Transactional revision/checkpoint fencing remains necessary even after pure validation.

## Required caller sequence before any future API integration

Authenticate and derive the owner before looking up a server-owned ledger or its events. Strictly parse the incoming event before comparing it with a durable event record. Resolve any existing event in the chosen owner/ledger event-ID scope against its canonical payload **before** applying current revision, checkpoint, content-version, or eligibility rules for a *new* event: an identical durable duplicate may have a historical base revision and checkpoint. The exact event-ID format and canonical encoding remain design decisions. For an unclaimed event, load the server-owned ledger with a durable pinned trusted book/version. The pure guard now checks the event version against `checkpoint.contentVersion` and looks up that pinned artifact, but a future caller must still verify the ledger's provenance, required shape, and eligibility. Do not use client-provided coins, achievements, derived state, awards, checkpoint, or projection. The guard's output is only a proposal: persist it through the transaction-backed adapter with the original expected checkpoint and revision, and reconcile ambiguous outcomes from durable event/ledger state. This sequence is a design requirement, **not** an implemented route.

A `nextSceneId` must be checked against trusted content before writing a new checkpoint. **Do not assume** that `endsBook` implies a particular scene ID or that the next book starts automatically: the existing reducer returns both fields but does not define the cross-book transition policy. A terminal checkpoint must not accept a normal choice until a separately specified transition authorizes it.

## Decisions and implementation gates that block broader progression

1. Enumerate lifecycle IDs in the exported registry and map each to a precise durable eligibility predicate (for example, book start or book completion); do not infer eligibility from a matching string alone.
2. Specify the opening grant amount, eligibility and event identity, and when `openingGranted` is persisted. Do not grant on ledger read or on a client-supplied cloud-save field.
3. Specify replay protection through `lifecycleApplied` and durable event IDs, including scope across books and content versions.
4. Define terminal and sequel transitions, including which event can change `checkpoint.bookId`, the initial scene for the next book, and whether a terminal book can be replayed.
5. Specify achievement ledger metadata and provenance before enabling achievement-bearing choices; the current guard deliberately rejects them rather than silently losing awards.
6. Implement separately approved clean, account-only ledger initialization; any legacy import requires a separate review. A client-controlled account or anonymous save is not an authoritative seed.
7. Implement and test full ledger-shape validation and authoritative ledger loading at the future trusted caller boundary. The pure guard now checks a supplied checkpoint version, but does not establish provenance, perform a migration, or make the public ledger schema versioned.

## Tests and remaining gates

The isolated pure tests cover a valid nonterminal choice without input mutation; a coin-spending choice with the existing reducer's zero-coin floor, flag and affinity changes; stale revisions; wrong, noncurrent, or terminal checkpoints; merge/fence/claim markers; inconsistent or invalid coin balances; mismatched or duplicate derived achievement IDs and preservation of matching recorded achievements; missing, invalid, mismatched and unavailable durable content-version pins; pin preservation in a proposed checkpoint; unknown choices and content versions; missing destinations; direct and affinity-derived achievement awards; and lifecycle-event rejection. Mongo reservation tests separately exercise transactional fencing and recovery. These tests do **not** establish authentication, duplicate-event ordering at a future endpoint, full ledger-schema validation, or production readiness.

**Review gate:** the four design directions have been approved with unresolved implementation specifics documented separately. Do not register a route merely because pure tests pass.
