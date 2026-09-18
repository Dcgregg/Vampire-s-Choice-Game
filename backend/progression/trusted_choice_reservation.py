"""Inert trusted choice reservation plan; never accept client projections.

The caller MUST obtain authenticated_user_id from a verified server session and
load ledger by its server-side identifier from the trusted store. This pure
function does not reserve, persist, authenticate sessions, or award players.
"""
from copy import deepcopy
from typing import Any, Mapping

from .canonical_event import canonical_event_sha256
from .choice_checkpoint_guard import CheckpointConflict, prepare_nonterminal_choice
from .strict_event_input import StrictChoiceEvent
from .trusted_owner import require_account_ledger_owner


def plan_account_choice_reservation(
    registry: Mapping[str, Any], trusted_ledger: Mapping[str, Any],
    event: StrictChoiceEvent, *, authenticated_user_id: str,
) -> dict:
    """Build reservation arguments solely from a verified owner and reducer.

    This is a single-choice plan, not a write API. The reservation adapter must
    still enforce unique event/revision indexes, checkpoint CAS, lease fencing,
    and transactional attribution. Do not use a client-supplied ledger.
    """
    owned = require_account_ledger_owner(
        trusted_ledger, authenticated_user_id=authenticated_user_id,
    )
    if not isinstance(event, StrictChoiceEvent):
        raise CheckpointConflict("strictly parsed choice event required")
    if owned.get("_id") is None:
        raise CheckpointConflict("persisted ledger ID required")
    retained = owned["appliedEventIds"]
    revision = owned["progressionRevision"]
    if (any(type(key) is not str or not key.isascii() or not key.isdecimal()
            or str(int(key)) != key or int(key) > revision
            or not isinstance(value, str) or not value
            for key, value in retained.items())
            or len(set(retained.values())) != len(retained)
            or (revision > 0 and str(revision) not in retained)):
        raise CheckpointConflict("trusted event attribution required")
    if event.eventId in retained.values():
        raise CheckpointConflict("event already attributed")
    proposal = prepare_nonterminal_choice(registry, owned, event)
    return {
        "ledger_id": owned["_id"],
        "expected_owner_type": "account",
        "expected_owner_id": authenticated_user_id,
        "event_id": event.eventId,
        "payload_hash": canonical_event_sha256(event.model_dump(mode="python")),
        "base_revision": revision,
        "awards": {"coins": proposal["nextProjection"]["coins"]["confirmed"] - owned["coins"]["confirmed"]},
        "next_projection": deepcopy(proposal["nextProjection"]),
        "expected_checkpoint": deepcopy(proposal["expectedCheckpoint"]),
    }
