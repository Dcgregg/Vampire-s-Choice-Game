# Phase 6C completion and cutover review

**Code status:** implementation complete on the draft Phase 6C branch. The
trusted backend and client flags remain disabled by default. This document is
not permission to merge, deploy, enable either flag, or modify live data.

## Pinned behavior

- A newly authenticated account gets exactly **50 server-authoritative
  BloodCoins**, fresh trusted achievements, and a Book 1 v1 checkpoint at
  `b1_c1_s1`. Browser saves never seed coins or achievements.
- `character_created` is the only enabled lifecycle transition. It is eligible
  only at that opening checkpoint, is marked as
  `book1:1:character_created`, and is idempotent by both event ID and marker.
- Choice rewards, direct achievements, affinity-derived achievements, flags,
  affinities, navigation, and terminal state are derived from the pinned
  trusted registry. Each new achievement stores a server millisecond timestamp
  and `source: awarded` in the same atomic projection as the derived ID.
- An `endsBook` choice keeps the registry-provided destination and marks the
  current checkpoint terminal. It does not infer a sequel, change content
  versions, or permit another ordinary choice.
- The client persists account-scoped event intent only. It never persists or
  predicts an authoritative reward. Confirmed rewards render from server
  responses; pending events are shown separately.
- A conflict or indeterminate result blocks new trusted choices. Reconciliation
  is explicit. A player may pause the account queue and sign out/switch
  accounts while local narrative progress and the account-scoped pending intent
  remain preserved.

## Security and reliability boundary

- Routes require the exact server flag `TRUSTED_PROGRESSION_ROUTES=enabled`;
  the client requires the exact independent flag
  `VITE_TRUSTED_PROGRESSION_ROUTES=enabled`.
- All mutating trusted routes require a verified session identity, strict
  Pydantic input, the non-simple `X-VC-Progression: 1` CSRF header, and a shared
  bounded 60-request/60-second per-process account limiter.
- Canonical payload hashes, ledger-scoped UUIDv4 event IDs, unique event and
  revision indexes, transactional checkpoint/revision CAS, durable attribution,
  and ambiguous-commit recovery prevent duplicate awards and cross-account
  writes.
- Outcome logs contain only event kind and stable status, not account IDs,
  balances, payloads, session values, or event IDs.

## Verification coverage

- Pure guards cover malformed authority, revision/version/checkpoint conflicts,
  achievement metadata, lifecycle eligibility/replay, and terminal completion.
- Route tests cover strict parsing, private stable errors, session-derived
  ownership, CSRF rejection, and rate limiting.
- Client tests cover lifecycle-before-choice ordering, offline persistence,
  confirmed-versus-pending rendering, account isolation, stale responses after
  logout, and safe conflict pause/retry behavior.
- Disposable replica-set Mongo tests cover concurrency, duplicate delivery,
  changed intent, ambiguous commit recovery, and an authenticated HTTP full-book
  path from 50 coins through terminal completion.
- The browser workflow covers a real Chromium cookie session through bootstrap,
  lifecycle, choice, CSRF rejection, FastAPI, and disposable MongoDB.

## Explicit cutover gates

The following require a separate approval and deployment environment; they are
not implied by green code or CI:

1. Review the draft PR and current workflow results, then explicitly approve a
   merge to `main`.
2. Verify the real OAuth provider and production origin/session-cookie/CORS
   configuration in staging. Automated tests use disposable, test-seeded
   sessions and never contact the external identity provider.
3. Configure centralized aggregation/alerts for trusted progression conflicts,
   indeterminate results, 429s, and 5xx responses. The application emits safe
   outcomes, but cannot provision deployment monitoring itself.
4. Confirm a transaction-capable MongoDB replica set, indexes, backup/restore,
   retained trusted Book 1 v1 content, and no pre-existing malformed account
   ledgers.
5. Enable the server flag in staging first, run the signed-in Book 1 smoke path,
   then enable the client flag. Production activation needs its own explicit
   decision and rollback owner. Rollback is both flags off; never delete ledgers
   or events during rollback.

