# Phase 6B trusted API acceptance matrix (INERT)

**Status:** implementation planning only. This is not a route, authorization to merge, scheduler, migration, or production readiness sign-off. Companion: `TRUSTED_API_CONTRACT_DRAFT.md`.

## Existing facts to preserve

- `server.py` already has `_current_user` and account-save routes, but `account_saves.playerState` is client supplied; neither it nor anonymous `playerId` proves a trusted progression balance.
- `contracts.py` currently permits extra event fields and defaults `baseProgressionRevision` to zero. The proposed API boundary needs a separate strict request model or deliberate contract hardening; do not assume these models already reject extras.
- `reducer.py` derives effects from pinned content, but `apply_lifecycle` checks only that an ID exists; the route must not interpret that as proof of eligibility.
- `MongoReservationStore.reserve` accepts caller-provided awards and projection, so **only a trusted server-side validator** may call it. `commit` requires a durable projection and expected checkpoint. Existing adapter tests are not HTTP authorization tests.

## Test cases to implement before registering any endpoint

| Area | Given / action | Required observable outcome | Gate |
| --- | --- | --- | --- |
| Authentication | Missing, expired or invalid session submits an event | No ledger or event write; stable unauthenticated response | Confirm auth/CSRF design |
| Ownership | Account A submits account B's ledger ID or an anonymous player ID | Identity is derived only from session; no cross-owner read/write or existence leak | Choose account-ledger identifier and lookup |
| Strict input | Extra `coins`, `awards`, `projection`, `ownerId`, `nextSceneId`, unknown fields, booleans in integer fields, oversize strings/body | Reject before reservation; no reward mutation | Pin limits and strict model |
| Content | Unknown book/version, scene or choice | Reject against pinned registry; no reservation that can later award | Define rejection persistence |
| Reachability | Valid choice exists but `fromSceneId` differs from durable checkpoint | Conflict/no award | Define checkpoint transition and terminal behavior |
| Lifecycle | Known lifecycle ID submitted before eligible or replayed after use | No award; server state determines eligibility | Define lifecycle state machine |
| Reward integrity | Client alters cloud-save coins/achievements or sends fake reward fields | Trusted ledger remains unchanged; server reducer is sole award source | Define clean ledger seed and legacy import policy |
| Idempotency | Same owner/event ID and canonical payload submitted twice | One revision/award; duplicate returns durable outcome | Pin digest fields and canonical encoding |
| Payload collision | Same owner/event ID with changed validated payload | Conflict; never reapply | Pin event ID namespace |
| Concurrency | Two distinct events reserve the same base revision | At most one advances; loser gets conflict/reconciliation response | Verify unique indexes and transactional deployment |
| Ambiguous commit | Transaction result or network fails after possible write | Never claim confirmed until durable state is reconciled; retry does not double-award | Pin error envelope and retry guidance |
| Recovery | Lease takeover races commit, or unexpected DB error aborts sweep | No stale-owner write; unresolved events retained; failure surfaced | Follow `RECOVERY_FAILURE_POLICY.md` |
| Legacy separation | Existing anonymous/account save is edited, claimed or overwritten | No direct trusted ledger mutation | Approve migration/import and ownership policy separately |

## Decisions to resolve in order

1. **Ledger initialization and provenance:** decide whether new accounts start from a clean server-seeded ledger; separately specify whether and how historical client-derived awards can be imported, including provenance and abuse limits. Do not silently promote a cloud save.
2. **State machine:** specify opening checkpoint, scene transitions, terminal/book transitions, and exact lifecycle eligibility and replay guards using trusted content and durable ledger state.
3. **Wire contract:** choose event-ID scope, canonical serialization, strict size/type bounds, rejection persistence, public response envelope, and conflict/indeterminate retry codes. Ensure a duplicate is checked against the durable event before treating its old base revision as stale.
4. **Security and operations:** review cookie CSRF protections, session handling, rate limiting, index verification, transaction-capable MongoDB, alerts, reconciliation, and rollout. Obtain explicit authorization before wiring any route or worker.

**Implementation sequence after review:** write pure strict-validation/state-machine tests first; add a server-side orchestrator tested against fake stores; add disposable-Mongo concurrency/integration tests; only then separately consider registering a route. All tests must run without production credentials. A green existing Phase 6B CI run does not certify these unimplemented cases.
