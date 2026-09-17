"""Pure, inert replay of strictly parsed ordinary choices from a trusted checkpoint.

Not an HTTP endpoint, ownership check, event store or migration validator. The
caller must load the initial ledger from a trusted store; never use a client
snapshot as the starting ledger. No terminal or achievement-awarding choices are
supported. A proposed projection is NOT authoritative until transactionally
persisted with identity, revision fencing and event deduplication.
"""
from copy import deepcopy
from typing import Any, Mapping, Sequence

from .choice_checkpoint_guard import CheckpointConflict, prepare_nonterminal_choice
from .strict_event_input import StrictChoiceEvent


def replay_nonterminal_choices(
    registry: Mapping[str, Any], trusted_ledger: Mapping[str, Any],
    events: Sequence[StrictChoiceEvent],
) -> dict:
    """Validate a bounded ordered sequence without mutating the trusted ledger.

    Every event must name the current checkpoint and revision; an event ID may
    appear only once in the supplied sequence. Durable event deduplication is
    still the responsibility of the future transactional event store.
    """
    if not isinstance(events, (list, tuple)) or not 1 <= len(events) <= 100:
        raise CheckpointConflict('expected one to one hundred choice events')
    proposed = deepcopy(dict(trusted_ledger))
    seen: set[str] = set()
    for event in events:
        if not isinstance(event, StrictChoiceEvent):
            raise CheckpointConflict('strictly parsed choice event required')
        if event.eventId in seen:
            raise CheckpointConflict('duplicate event ID in replay')
        seen.add(event.eventId)
        proposal = prepare_nonterminal_choice(registry, proposed, event)
        proposed.update(proposal['nextProjection'])
        proposed['progressionRevision'] += 1
    return proposed
