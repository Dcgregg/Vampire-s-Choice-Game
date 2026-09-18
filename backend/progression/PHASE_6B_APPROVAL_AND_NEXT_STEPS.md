# Phase 6B approval and implementation gates

**Approval recorded:** 2026-09-16. The project owner approved the four design directions in `PHASE_6B_DECISION_RECORD_DRAFT.md`. This records approval of the principles below, **not** unspecified values or permission for live activation. The draft remains the detailed design reference; this file records the approval boundary.

## Approved design directions

1. **Clean account-owned ledger:** initialize at most one server-owned ledger per authenticated account from trusted content, not browser-controlled cloud saves. Do not import historical client coins or achievements in the first release. Keep legacy saves separate. Initialization is a separate idempotent operation, not an implicit event retry or ledger read.
2. **Durable content pin:** require a server-owned positive integer `checkpoint.contentVersion`; verify the pinned book/version/scene against retained trusted content. New choice events must match the durable book and version. No silent version upgrades; only an explicitly authorized atomic book transition may change the pin. This is a new schema requirement, not an assertion that existing ledgers already have it.
3. **Ledger-scoped event identity:** authenticate, strictly parse and canonicalize, resolve an existing `(ledgerId,eventId)` before *new-event* revision/checkpoint/version checks, reject same-ID changed payload, and reconcile in-flight/ambiguous outcomes without double awards. Never recycle a durably claimed ID.
4. **Staged story transitions:** no implicit opening grant; opening grant must be once-only and transactional. Lifecycle eligibility must be proven from durable state, achievements must update derived and metadata records atomically, and terminal/sequel transitions require their own explicit rules. Keep currently unsupported event paths fail-closed.

## Still unspecified: do not infer approval

- Exact opening book/scene, grant amount and grant event identity; verify values against exported trusted content.
- Event-ID format/length, byte-exact canonical encoding and fixtures, handling of pre-reservation rejections, response envelope and retry codes.
- Lifecycle IDs and durable eligibility predicates; achievement timestamp/provenance details; terminal and sequel/replay policy.
- Auth/CSRF and operational controls; schema migration/backfill, indexes/rollout, production credentials, route registration, worker activation, merge or deployment.

## Next isolated work, in order

1. Add pure tests for a required durable content pin (missing, invalid, mismatched and unavailable pinned artifact); then implement a fail-closed pin check in the inert ordinary-choice guard. Update synthetic checkpoints and any affected adapter fixtures together, and run the full Phase 6B CI.
2. Define and test a strict canonical event representation with cross-language fixtures **only after** the exact encoding and ID bounds are selected; do not invent them in code.
3. Add pure validation for the approved clean ledger shape without creating a ledger, seeding rewards or reading cloud saves. Test concurrent initialization only once an isolated initializer contract is specified.
4. After the remaining story values are resolved, test and implement achievement metadata, opening grant, lifecycle eligibility and terminal transitions incrementally against fake stores and disposable MongoDB. A trusted caller must be tested before any route is considered.

**Safety boundary:** This approval does not authorize creating real ledgers, importing or migrating saves, initializing authoritative collections, registering an endpoint, running recovery, merging into `main`, or deploying. Keep existing client cloud saves untrusted for coins and achievements. Green CI covers only implemented tests, not these future capabilities.
