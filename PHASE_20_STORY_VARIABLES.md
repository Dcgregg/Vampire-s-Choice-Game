# Phase 20 — Story variables and dynamic text

Private drafts support four controlled dynamic-text tokens:

- `{{player.name}}`
- `{{player.subject}}`
- `{{player.object}}`
- `{{player.possessive}}`
- `{{player.species}}`
- `{{speaker.name}}` (inside a dialogue beat)

The private playtest includes a test name and pronoun selector. Tokens are
resolved there, while the backend rejects unknown token names during manual,
AI-generated and Book-JSON draft validation. Tokens are data only; expressions
and JavaScript are not supported.

## Draft lifecycle

Administrators can archive a draft to hide it from active editing, restore it
back to an editable private draft, or permanently delete it after a browser
confirmation. Archived drafts cannot be edited until restored. Restoring clears
the current release approval, so every restored draft must pass review again.
None of these actions writes to player-facing content.

## Structured dialogue

Each private draft scene can include dialogue beats with a stable speaker ID,
editable display name, text and mood. The private playtest renders these as
distinct talk boxes and resolves the same controlled tokens. Portraits,
relationship-aware variants and story-defined numeric values are deliberately
left for the next Phase 20 increment.
