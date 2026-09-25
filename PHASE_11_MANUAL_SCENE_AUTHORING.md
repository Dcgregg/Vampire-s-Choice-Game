# Phase 11 — Manual scene authoring

Story Admin now supports manual scenes and choices within a draft. This phase
does not connect drafts to the player-facing story, so working in the editor
cannot change a live playthrough.

## Writing a scene

1. Sign in with the allow-listed administrator account and open **Story Admin**.
2. Create or select a draft, then save its basic details.
3. In **Manual scenes & choices**, choose **Add scene**.
4. Give the scene a stable ID (letters, numbers, `_` and `-` only), chapter,
   title and story text.
5. Add player choices. Each choice needs its own ID and visible text. Set a
   **Next scene ID** to link it to another scene, or leave it blank to end that
   route. **Private consequence notes** are for editorial planning only.
6. Choose **Save scenes**, then **Check draft** to identify missing scenes or
   broken destination IDs.

## Safeguards

- Only allow-listed admins can read or write drafts.
- Scene and choice IDs must be unique within the draft/scene.
- The API limits scene, choice and text sizes to keep draft data bounded.
- Saving uses the draft revision, preventing a stale browser tab from silently
  overwriting someone else's edits.
- Publication remains unavailable; a later phase will provide a deliberate
  review-and-publish flow.
