# Phase 4 — Persistence & Sync Architecture

## Data flow
```
React UI
  → GameStateManager (host, local state + localStorage)      [src/state/gameState.ts]
      → Story Engine (pure, NO network/db)                    [src/engine/*]
      → SyncManager (local-first, sits ABOVE local save)      [src/sync/*]
          → cloudClient (fetch /api/saves)                    [src/sync/cloudClient.ts]
              → FastAPI save API  (/api/*)                    [backend/server.py]
                  → MongoDB (collection: cloud_saves)
```
The Story Engine never imports networking or the database. Cloud sync is invoked
only by the host (`notify()`), never inside the engine. The game is fully
playable with the backend unavailable (local storage remains the source of truth).

## Backend choice
- **FastAPI**: already provisioned in this environment, async, first-class Pydantic
  validation for typed request/response and useful 4xx errors, tiny surface for a
  narrow save API. Strongest fit vs. adding a new framework.
- **MongoDB**: `PlayerState` is a nested, evolving document (flags/relationships/
  progress) — a document store maps 1:1 with no schema migrations for content
  shape changes, and one save = one document keyed by anonymous player id. Async
  `motor` driver is already present. Operational complexity is minimal (single
  collection, single-document reads/writes, one unique key).

## Anonymous identity
- `vc_` + hex UUID, generated client-side, stored in `localStorage: vc_player_id`.
  No PII. Used ONLY as the cloud-save key; never as authentication.
- Limitation (documented): a browser-local id gives cloud persistence for that
  identity but NOT reliable cross-device recovery. That needs a real account.

## Versioning (three independent axes — unchanged from Phase 3)
- content schema version, per-book `version` (content layer)
- player **save** schema version (`PlayerState.version` = 3)
Saves carry `contentVersions[bookId]`; the cloud record stores `saveSchemaVersion`
+ `contentVersions` so future migrations can detect stale saves per book.

## Cloud save record (MongoDB `cloud_saves`)
```
{ _id (internal, never returned), playerId, saveSchemaVersion,
  contentVersions, playerState (PlayerState v3), revision (int),
  createdAt (ISO), updatedAt (ISO) }
```
Story content is NOT duplicated in saves — it stays in the separately-versioned
content layer.

## API (all under /api)
- `GET  /api/health` → `{ status, db, time }`
- `GET  /api/saves/{playerId}` → save or `404 {error:not_found}`
- `PUT  /api/saves/{playerId}` (body: `{saveSchemaVersion, contentVersions, playerState, baseRevision}`)
  - creates when none exists (baseRevision must be 0) → `revision:1`
  - updates only when `baseRevision === server.revision` → `revision+1`
  - otherwise `409 {error:revision_conflict, currentSave}`

## Conflict / revision strategy (optimistic concurrency)
| Situation           | Behaviour                                                        |
|---------------------|------------------------------------------------------------------|
| local only          | push creates cloud save (rev 1)                                  |
| cloud only          | client adopts cloud on start                                     |
| identical revisions | accepted; if payload unchanged, push is skipped                  |
| local newer         | base == server.revision → accepted, revision bumped              |
| cloud newer         | 409 → client adopts newer cloud save (cloud wins for stale)      |
| stale update        | 409 → same adopt-cloud resolution                                |
| backend unavailable | stay local, status=offline, retry later; gameplay never blocks   |

No field-by-field story merge (not needed). A stale client can never silently
overwrite newer cloud progress.

## Security boundary (this phase)
- Payload structure validated (Pydantic); body size capped (512 KB); player-id
  format enforced; internal `_id` never returned; DB creds server-side only;
  CORS configurable; anonymous id NOT trusted for security/purchases.
- **Blood Coins and achievements remain CLIENT-DERIVED and are NOT tamper-proof.**
  They must NOT be treated/marketed as server-authoritative until a later phase
  adds trusted server-side economy operations.

## Future account upgrade (design only — not implemented)
Add `userId` to the save document and an auth-guarded `POST /api/saves/{id}/claim`
that attaches an anonymous save to an authenticated user (verify ownership, set
`userId`, keep same document/revision). The Story Engine and content model are
untouched: identity/ownership lives entirely in the persistence layer.

## Offline / PWA
Local play and existing PWA precache are unchanged. Sync API responses are NOT
added to any service-worker cache (dynamic, per-identity). Failures degrade
gracefully to local-only.
