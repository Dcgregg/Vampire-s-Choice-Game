# Phases 17–19 — Release preparation

This bundled milestone prepares approved drafts for a future, separately
authorised publication phase. It cannot publish story content.

## Phase 17 — Story graph integrity

Readiness checks now prevent unreachable scenes, routes that can never reach an
ending, and stories with no terminal scene.

## Phase 18 — Release readiness gate

The strengthened checks are used before an approval or a downloadable package
can be created. This keeps editorial review and release preparation aligned.

## Phase 19 — Release package

Downloading an approved draft now produces a `release-package/v1` JSON file
with its source revision, scene count, and a SHA-256 checksum. It is still
marked `playerFacing: false` and `published: false`.
