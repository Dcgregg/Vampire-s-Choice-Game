# Phase 6B trusted state-machine review (INERT)

**Status:** design and test planning only. This file does not approve ledger initialization, register an endpoint, schedule recovery, or authorize migration or deployment. Read alongside `TRUSTED_API_CONTRACT_DRAFT.md` and `TRUSTED_API_ACCEPTANCE_MATRIX.md`.

## Observed implementation boundary

- `strict_event_input.py` validates the event's shape, required revision, types, and provisional string limits. It does **not** validate authentication, content, checkpoint reachability, or lifecycle eligibility.
- `trusted_content.book_entry` pins a `(bookId, contentVersion)`; `reducer.apply_choice` checks that the named scene and choice exist and derives the resulting awards and `nextSceneId`/`endsBook`. It does **not** compare the source scene to a durable checkpoint.
- `reducer.apply_lifecycle` checks only that a lifecycle ID exists and unlocks its achievement when present. Existence alone is not permission to award.
- `MongoReservationStore.reserve` can accept a caller-supplied projection and awards. Its caller must be trusted and must validate against a durable ledger; the adapter is not an eligibility validator.

## Candidate pure choice guard (not implemented)

For a *new* event, first resolve any existing `(ledgerId, eventId)` against the canonical payload; an identical durable duplicate must be handled before rejecting its historical base revision. For an unclaimed event, require a server-owned ledger and a pinned trusted book/version; require the event's base revision to equal the ledger revision, the ledger to be unfenced, the checkpoint to be nonterminal, and `bookId`/`fromSceneId` to equal the ledger's checkpoint. Verify the choice on that exact scene in the pinned registry. Compute effects on a copy of the durable derived state; never mutate the original before successful persistence. Build `expectedCheckpoint` from the full durable checkpoint and `nextProjection` from the reducer output, then let the transaction-backed adapter recheck revision and checkpoint at commit. No client-supplied projection or reward may reach `reserve`.

A `nextSceneId` must be checked against trusted content before writing a new checkpoint. **Do not assume** that `endsBook` implies a particular scene ID or that the next book starts automatically: the existing reducer returns both fields but does not define the cross-book transition policy. A terminal checkpoint must not accept a normal choice until a separately specified transition authorizes it.

## Decisions that block a lifecycle guard

1. Enumerate lifecycle IDs in the exported registry and map each to a precise durable eligibility predicate (for example, book start or book completion); do not infer eligibility from a matching string alone.
2. Decide when opening grants happen, how `openingGranted` is persisted, and whether a lifecycle event consumes a progression revision. Do not grant on ledger read or on a client-supplied cloud-save field.
3. Define replay protection via `lifecycleApplied`, the durable event ID, or both; specify how these interact across books and content versions.
4. Define terminal and sequel transitions, including which event can change `checkpoint.bookId`, the initial scene for the next book, and whether a terminal book can be replayed.
5. Approve clean ledger initialization and any legacy import separately; a client-controlled account or anonymous save is not an authoritative seed.

## Pure tests to add after the decisions are pinned

- Valid choice at the exact durable checkpoint derives the trusted next state without mutating the input ledger; invalid scene, choice, or content version does not award.
- A choice from a real but noncurrent scene, a stale revision, a terminal checkpoint, or a different book cannot advance.
- A malformed or missing next scene is rejected before reservation unless an explicitly defined terminal transition permits it.
- An identical already-applied event returns its durable outcome before stale-base validation; same event ID with changed payload conflicts.
- Every lifecycle ID has positive eligibility, early/late submission, replay, and cross-book tests; an unknown ID never awards.
- A failed validation leaves both event collection and ledger unchanged. A race after validation still loses safely at the adapter's transactional revision/checkpoint fence.

**Review gate:** obtain explicit choices for the unresolved lifecycle, opening, terminal, and ledger-seeding rules before implementing a general state machine. The choice guard can be implemented and tested independently once the checkpoint and terminal rules are pinned. Do not register a route merely because pure tests pass.
