# Phase 6B merge readiness — 2026-09-17

**Verdict: NOT ready to merge as a completed, playable Phase 6B.** This is a review record, not a production activation plan or permission to merge. The current PR is explicitly an inert foundation. Five existing workflows passed at commit `80dd42a27598a153b285f6e86edc98e52fc6aa3f`; they do not establish end-to-end safety or production readiness.

## Verified implementation boundaries

- Isolated trusted progression guards, attribution, transactional prototypes, and regression suites exist. Review the actual code and CI for their precise coverage; do not infer live integration.
- The new story-only claim router is not registered in `backend/server.py`. Its optional ownership verifier denies every request when absent. The frontend story-only coordinator is not connected to `AuthContext`.
- `anonymous_claim_proof.py` issues random credentials and verifies stored digests; `anonymous_credential_issuance.py` can create a new server-ID save in isolation. Neither is connected to the existing anonymous GET/PUT API or the browser's identity lifecycle. Existing saves have no proof digest.
- The existing `/api/me/claim` and `use_anonymous` strategy remain the live account-linking path. Their client-derived rewards and nontransactional transfer must not become a trusted ledger source.

## Merge-blocking acceptance work

1. **Define the release scope explicitly.** A review-only merge of inert infrastructure is a separate decision from declaring Phase 6B feature-complete. Do not relabel this PR feature-complete while routes and UI are disconnected.
2. **Anonymous proof lifecycle:** implement and test a server-generated identity/credential issuance endpoint, secure delivery and client persistence, authenticated anonymous reads/writes, safe rotation/revocation and recovery. Establish a non-impersonating legacy-save transition; player ID and revision alone cannot bootstrap proof. Protect proof from URL/log exposure and consider XSS, CSRF and device loss.
3. **Atomic ownership:** verify the credential and revision inside the same MongoDB claim transaction as the account insert and anonymous ownership stamp. A pre-transaction verifier alone is subject to rotation/revocation races. Test simultaneous claim, rotation, stale revision, cross-account replay and ambiguous commit outcomes against a disposable transaction-capable deployment.
4. **Conflict and lifecycle UX:** implement explicit account-versus-anonymous comparison, keep both saves until resolution, provide cancellation, offline/retry and second-device restore. Prevent local auto-push and mode switches after failed or unresolved claims; test logout/account switching.
5. **Trusted progression cutover:** implement an authenticated API caller and safe event persistence end-to-end, not just isolated adapters. Confirm trusted content eligibility, opening grant, achievement metadata, terminal/sequel/replay rules and that browser reward fields never initialize or mutate the authoritative ledger.
6. **Release verification:** update acceptance tests for full browser-to-API-to-disposable-Mongo flows, review indexes, transaction support, secrets, observability, rollback and existing-player migration. Confirm all required CI checks on the final HEAD and compare with current `main`; arrange security and product review before any activation.

## Immediate safety rule

Do not register the story-only route with a verifier that trusts only `playerId`, revision or a pre-transaction read. Do not silently backfill credentials for legacy saves. Do not merge, deploy, migrate player data, initialize real ledgers or award real players on the strength of this document or green isolated tests.
