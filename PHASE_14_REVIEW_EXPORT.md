# Phase 14 — Review export

Phase 14 adds a deliberate hand-off between draft authoring and any future
publishing work. It does **not** make drafts playable or change player-facing
story content.

## Export a draft for review

1. In **Story Admin**, select the draft.
2. Use **Check draft** and resolve any reported issues.
3. Choose **Ready for review**.
4. Choose **Download review JSON**.

The downloaded package includes the draft, its revision, its scenes and
editorial notes. It is marked `playerFacing: false` and `published: false`.
Only allow-listed Google-authenticated administrators can request it.

## Safeguards

- The export route accepts only drafts in `ready_for_review`.
- It repeats the server-side readiness checks before exporting.
- It has no code path that writes the trusted story registry or player saves.
- A later, explicit phase would need a separately reviewed publication process.
