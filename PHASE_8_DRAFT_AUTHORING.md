# Phase 8 draft authoring

Phase 8 adds a small, admin-only planning workspace. It is intentionally not a
publishing system.

- Access still requires a valid Google session and an email in `ADMIN_EMAILS`.
- Drafts live in MongoDB's `admin_drafts` collection, separate from player
  saves and the checked-in trusted-content registry.
- The API uses revisions to reject concurrent overwrites.
- The player app never reads drafts. Publishing playable scenes remains a later
  explicit review/export step.

No additional environment variables are required beyond the Phase 7 admin
allowlist and the existing MongoDB connection.
