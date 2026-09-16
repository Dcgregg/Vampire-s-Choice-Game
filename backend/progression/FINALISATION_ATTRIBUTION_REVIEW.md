# Phase 6B: event-to-ledger attribution review (unresolved)

**Status: merge/activation blocker for trusted awards.** This is a review note, not a fix or permission to activate the inert adapter.

## Observed code path

`MongoReservationStore.finalise()` calls `decide_retry()` with the reservation's target revision and the current ledger revision. `decide_retry()` returns `FINALISE` whenever the ledger revision is at least the reserved target. `recover()` similarly treats `ledger.progressionRevision >= event.targetRevision` as grounds to call `finalise()`. In `commit()`, a failed ledger CAS can return the current ledger when its revision has reached the target. None of these paths independently proves that the reserved event's durable `nextProjection` was written by that event.

The intended design assumes that **every** ledger revision has exactly one durable reservation, reservations are never deleted or reassigned, and the adapter is the only revision writer. The unique `(ledgerId,targetRevision)` index enforces one *reserved event* per revision, but does not itself prevent an unreserved or external ledger revision write. The current tests do not establish this exclusivity for all future writers.

## Required resolution before activation

1. Establish a durable attribution invariant for the committed revision, such as an atomic ledger marker identifying the event/reservation that wrote it, with a defined retention and validation contract. Do not infer authorship from `revision >= target` alone.
2. Specify how finalisation and recovery prove attribution after later legitimate revisions, when the original projection no longer matches the current ledger. A comparison to the latest projection alone is insufficient.
3. Make `commit()` fail closed when its CAS misses unless it can prove this same reservation already committed. A higher revision is not proof by itself.
4. Add disposable-MongoDB tests for a same-revision foreign write, a higher-revision foreign write, a genuine commit followed by later legitimate events, an ambiguous transaction result, and recovery after a crash. Assert no falsely applied event or award.
5. Review and test the single-writer boundary, index creation, and migration/rollback plan separately before any live route, worker or production collection is enabled.

**Illustrative failure scenario (not a passing test):** reserve event A for revision 1 with a reward projection; an unreserved writer advances the ledger to revision 1 without A's reward; `finalise(A)` sees `revision >= 1` and can label A `applied`. The same ambiguity exists at higher revisions. Do not report exactly-once awards or production readiness until the attribution invariant is implemented and tested.

No live API registration, merge, migration, production credentials or deployment is authorized by this note.
