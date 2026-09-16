# Phase 6B attributed adapter handover (inert)

## Verified in disposable MongoDB

`AttributedMongoReservationStore` in `attributed_mongo_reservations.py` uses the event lease fence and `write_attributed_revision` in the **same MongoDB transaction**. Its commit path never treats `progressionRevision >= targetRevision` alone as proof: a missed CAS can only reconcile after `require_event_attribution` matches the exact ledger, target revision and event ID. Finalisation uses `finalise_attributed_event`; recovery checks the same proof, including already-applied retries. The clean initializer seeds an empty `appliedEventIds` history for new ledgers. The dedicated integration suite covers commit/finalise idempotency, foreign writes at the target and later revisions, foreign commit rejection, recovery after commit, expired-lease recovery, and missing attribution history. Phase 6B progression CI run 35118512090 passed 189 selected tests.

## Still blocked before activation or merge as a playable feature

- The original `MongoReservationStore` retains revision-only success inference. Do **not** instantiate it for trusted awards. The new attributed subclass is opt-in and not registered as a live route; switching call sites requires a separate reviewed change and regression coverage. Existing tests of the legacy adapter do not establish attribution safety.
- Enforce a single authorized ledger writer at the database and application boundary. A foreign writer with write permission could forge or delete `appliedEventIds`; a matching marker alone is not cryptographic proof or a database permission boundary.
- Do not promote existing client saves or legacy ledgers. They may lack history. Define a separately approved migration or clean-start policy; no migration is implemented here.
- Review retention and document growth for per-revision `appliedEventIds` before long-running production use, including BSON document limits and audit/archival strategy.
- Add concurrency/fault-injection coverage for ambiguous commit results, lease takeovers and finalisation races specifically against the attributed adapter. The older adapter's tests cannot substitute for these.
- Validate trusted caller authentication/authorization, canonical event hash and server-side projection provenance; settle opening-grant amount/eligibility, achievements, content-version lifecycle, terminal/sequel semantics and rollout/rollback plan.
- The older strict-xfail blocker file is **not included** in the progression workflow; inspect and replace it with positive attributed-adapter regressions before treating the entire historical defect suite as cleared.

No production credentials, API activation, deployment, migration or PR merge is authorized by this document.
