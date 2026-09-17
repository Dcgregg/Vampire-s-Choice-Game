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

    Event IDs must not occur in either the supplied sequence or the trusted
    ledger's retained attribution map. The returned attribution is a proposal,
    not proof of durable deduplication or an authorized write.
    """
    if not isinstance(events, (list, tuple)) or not 1 <= len(events) <= 100:
        raise CheckpointConflict('expected one to one hundred choice events')
    if not isinstance(trusted_ledger, Mapping):
        raise CheckpointConflict('trusted ledger required')
    retained = trusted_ledger.get('appliedEventIds')
    revision = trusted_ledger.get('progressionRevision')
    if (not isinstance(retained, Mapping) or type(revision) is not int or revision < 0
            or any(type(key) is not str or not key.isascii() or not key.isdecimal()
                   or str(int(key)) != key or int(key) > revision
                   or not isinstance(event_id, str) or not event_id
                   for key, event_id in retained.items())):
        raise CheckpointConflict('trusted event attribution required')
    if len(set(retained.values())) != len(retained):
        raise CheckpointConflict('duplicate trusted event attribution')
    proposed = deepcopy(dict(trusted_ledger))
    proposed['appliedEventIds'] = dict(retained)
    seen: set[str] = set(retained.values())
    for event in events:
        if not isinstance(event, StrictChoiceEvent):
            raise CheckpointConflict('strictly parsed choice event required')
        if event.eventId in seen:
            raise CheckpointConflict('duplicate or previously applied event ID')
        seen.add(event.eventId)
        proposal = prepare_nonterminal_choice(registry, proposed, event)
        next_revision = proposed['progressionRevision'] + 1
        if str(next_revision) in proposed['appliedEventIds']:
            raise CheckpointConflict('next revision already attributed')
        proposed.update(proposal['nextProjection'])
        proposed['progressionRevision'] = next_revision
        proposed['appliedEventIds'][str(next_revision)] = event.eventId
    return proposed
