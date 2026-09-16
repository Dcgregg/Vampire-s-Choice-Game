# Phase 6B trusted state-machine review (INERT)

**Status:** an isolated, pure, nonterminal choice guard is implemented and tested; this is **not** approval to initialize ledgers, register an endpoint, schedule recovery, migrate saves, merge into `main`, or deploy. Read alongside `TRUSTED_API_CONTRACT_DRAFT.md` and `TRUSTED_API_ACCEPTANCE_MATRIX.md`.

## Observed implementation boundary

- `strict_event_input.py` validates the event's shape, required revision, types, and provisional string limits. It does **not** validate authentication, content, checkpoint reachability, or lifecycle eligibility.
- `trusted_content.book_entry` pins a `(bookId, contentVersion)` against the trusted registry; `reducer.apply_choice` checks that the named scene and choice exist and derives awards and `nextSceneId`/`endsBook`. The reducer does **not** compare the source scene to a durable checkpoint.
- `choice_checkpoint_guard.prepare_nonterminal_choice` is a **pure proposal builder**, not an event processor or authorization boundary. It checks a server-loaded ledger's revision, book/source checkpoint, nonterminal state, merge/fence/claim markers, confirmed-versus-derived coin consistency, and agreement between the recorded achievement IDs and the derived achievement list (including rejection of duplicate derived IDs). It derives on a copy, rejects terminal and achievement-awarding choices, verifies the next scene exists, and returns an expected checkpoint and proposed projection. Its tests run in the isolated Phase 6B workflow. These checks are **not** full ledger-schema or achievement-metadata validation. The guard does not fetch or authenticate a ledger, resolve duplicate events, prove the ledger's content-version pin, reserve/commit an event, or define lifecycle or terminal transitions. Its caller must do the missing work before any trusted write.
- `reducer.apply_lifecycle` checks only that a lifecycle ID exists and unlocks its achievement when present. Existence alone is not permission to award.
- `MongoReservationStore.reserve` can accept caller-supplied projection and awards. Its caller must be trusted and must validate against a durable ledger; the adapter is not an eligibility validator. Transactional revision/checkpoint fencing remains necessary even after pure validation.

## Required caller sequence before any future API integration

Authenticate and derive the owner before looking up a server-owned ledger or its events. Strictly parse the incoming event before comparing it with a durable event record. Resolve any existing event in the chosen owner/ledger event-ID scope against its canonical payload **before** applying current revision, checkpoint, content-version, or eligibility rules for a *new* event: an identical durable duplicate may have a historical base revision and checkpoint. The exact event-ID scope and canonical encoding remain design decisions. For an unclaimed event, load the server-owned ledger with a durable pinned trusted book/version. Verify the event version matches that ledger pin; looking up a valid version in the registry alone does not prove the ledger is pinned to it. Check the ledger's required shape and eligibility before invoking the pure guard. Do not use client-provided coins, achievements, derived state, awards, checkpoint, or projection. The guard's output is only a proposal: persist it through the transaction-backed adapter with the original expected checkpoint and revision, and reconcile ambiguous outcomes from durable event/ledger state. This sequence is a design requirement, **not** an implemented route.

A `nextSceneId` must be checked against trusted content before writing a new checkpoint. **Do not assume** that `endsBook` implies a particular scene ID or that the next book starts automatically: the existing reducer returns both fields but does not define the cross-book transition policy. A terminal checkpoint must not accept a normal choice until a separately specified transition authorizes it.

## Decisions that block broader progression

1. Enumerate lifecycle IDs in the exported registry and map each to a precise durable eligibility predicate (for example, book start or book completion); do not infer eligibility from a matching string alone.
2. Decide when opening grants happen, how `openingGranted` is persisted, and whether a lifecycle event consumes a progression revision. Do not grant on ledger read or on a client-supplied cloud-save field.
3. Define replay protection via `lifecycleApplied`, the durable event ID, or both; specify how these interact across books and content versions.
4. Define terminal and sequel transitions, including which event can change `checkpoint.bookId`, the initial scene for the next book, and whether a terminal book can be replayed.
5. Define achievement ledger metadata and provenance before enabling achievement-bearing choices; the current guard deliberately rejects them rather than silently losing awards.
6. Approve clean ledger initialization and any legacy import separately; a client-controlled account or anonymous save is not an authoritative seed.
7. Define and test the durable content-version pin and full ledger-shape validation at the future trusted caller boundary; registry lookup alone is insufficient.

## Tests and remaining gates

The isolated pure tests cover a valid nonterminal choice without input mutation; a coin-spending choice with the existing reducer's zero-coin floor, flag and affinity changes; stale revisions; wrong, noncurrent, or terminal checkpoints; merge/fence/claim markers; inconsistent or invalid coin balances; mismatched or duplicate derived achievement IDs and preservation of matching recorded achievements; unknown choices and content versions; missing destinations; direct and affinity-derived achievement awards; and lifecycle-event rejection. Mongo reservation tests separately exercise transactional fencing and recovery. These tests do **not** establish authentication, duplicate-event ordering at a future endpoint, durable version pinning, full ledger-schema validation, or production readiness.

**Review gate:** obtain explicit choices for unresolved lifecycle, opening, terminal, achievement, and ledger-seeding rules before implementing a general state machine. Do not register a route merely because pure tests pass.
