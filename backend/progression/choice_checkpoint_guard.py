"""Inert Phase 6B pure guard for ordinary, nonterminal choice events.

No route, database access, event deduplication, lifecycle awards or terminal
transition is implemented here. The caller must load the ledger from a trusted
store and resolve an existing event ID before invoking this function.
"""
from copy import deepcopy
from typing import Any, Dict

from .reducer import apply_choice
from .trusted_content import InvalidChoice, book_entry


class CheckpointConflict(ValueError):
    """The proposed choice cannot advance the supplied durable checkpoint."""


def prepare_nonterminal_choice(
    registry: Dict[str, Any], ledger: Dict[str, Any], event: Any
) -> Dict[str, Any]:
    """Return a proposed next projection without modifying the input ledger.

    ``event`` must be a strictly parsed choice event; ``ledger`` must be
    server-loaded. The caller owns identity, deduplication, transactional
    fencing and persistence. Achievement metadata and terminal transitions
    are not yet specified, so choices that unlock achievements fail closed.
    """
    if event.kind != "choice":
        raise CheckpointConflict("only ordinary choice events are supported")
    checkpoint = ledger["checkpoint"]
    if ledger.get("fenced") or checkpoint.get("terminal"):
        raise CheckpointConflict("ledger is fenced or checkpoint is terminal")
    if event.baseProgressionRevision != ledger["progressionRevision"]:
        raise CheckpointConflict("progression revision changed")
    if event.bookId != checkpoint["bookId"] or event.fromSceneId != checkpoint["currentSceneId"]:
        raise CheckpointConflict("choice does not match durable checkpoint")

    book = book_entry(registry, event.bookId, event.contentVersion)
    derived = deepcopy(ledger["derived"])
    result = apply_choice(
        registry, derived, event.bookId, event.contentVersion,
        event.fromSceneId, event.choiceId,
    )
    if result["endsBook"]:
        raise CheckpointConflict("terminal choice transition is not specified")
    if result["awarded"] or set(derived["achievements"]) != set(ledger["achievements"]):
        raise CheckpointConflict("achievement ledger metadata is not specified")
    next_scene = result["nextSceneId"]
    if not isinstance(next_scene, str) or next_scene not in book["scenes"]:
        raise InvalidChoice("choice destination is not a trusted scene")

    next_checkpoint = {
        **deepcopy(checkpoint), "currentSceneId": next_scene, "terminal": False,
    }
    return {
        "expectedCheckpoint": deepcopy(checkpoint),
        "nextProjection": {
            "coins": {"confirmed": derived["coins"]},
            "achievements": deepcopy(ledger["achievements"]),
            "derived": derived,
            "checkpoint": next_checkpoint,
        },
        "awarded": [],
    }
