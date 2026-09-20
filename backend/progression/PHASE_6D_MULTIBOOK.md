# Phase 6D: Multi-book progression

Phase 6D adds the transition contract between completed books. It does not
publish or invent Book II content.

## Authority boundary

- The client submits only the lifecycle identity `start_next_book`.
- The server derives the target from the ordered trusted series registry.
- A transition is accepted only from a terminal checkpoint to the immediate
  next book when that book is marked `available` and has trusted content.
- Coins, achievements, affinity and flags are copied unchanged.
- The source book/version transition marker is persisted in `lifecycleApplied`;
  duplicate events and stale terminal checkpoints fail closed.

## Publishing a sequel

1. Add and validate the new book bundle in the content loader.
2. Mark its series entry `available`.
3. Regenerate `backend/trusted_content/registry.json`.
4. Run frontend parity, backend checkpoint, type and production-build checks.

Until all three content conditions agree, the completion screen shows the
coming-soon state and the authoritative server refuses the transition.
