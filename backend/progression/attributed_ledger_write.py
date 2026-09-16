"""INERT candidate for an attributed ledger CAS; not called by live routes or adapter.

The caller must hold the event's fenced lease in the SAME MongoDB transaction.
Only a trusted projection and exact expected checkpoint may reach this helper.
An unreserved writer can still bypass it; single-writer enforcement is a
separate activation gate. Never use this helper to migrate existing ledgers.
"""
from __future__ import annotations

from typing import Any, Mapping

from pymongo import ReturnDocument

from .attribution import AttributionUnproven, require_event_attribution


async def write_attributed_revision(
    ledgers: Any, *, event: Mapping[str, Any], projection: Mapping[str, Any],
    expected_checkpoint: Mapping[str, Any], session: Any,
) -> dict:
    """CAS the projection and event identity together, or fail without a write.

    Requires an initialized, retained ``appliedEventIds`` mapping. Every
    non-opening revision must retain attribution for its immediately preceding
    revision. This is a local continuity check, not proof of the entire history
    or protection against an unauthorized ledger writer. No upsert, implicit
    initialization, revision guessing, or post-CAS success inference.
    """
    base, target = event.get("baseRevision"), event.get("targetRevision")
    ledger_id, event_id = event.get("ledgerId"), event.get("eventId")
    if type(base) is not int or base < 0 or type(target) is not int or target != base + 1:
        raise AttributionUnproven("invalid reserved revision")
    if ledger_id is None or not isinstance(event_id, str) or not event_id:
        raise AttributionUnproven("missing event identity")
    if not isinstance(projection, Mapping) or set(projection) - {
        "coins", "achievements", "derived", "checkpoint", "lifecycleApplied", "openingGranted"
    } or not {"coins", "achievements", "derived", "checkpoint"}.issubset(projection):
        raise AttributionUnproven("invalid trusted projection")
    if not isinstance(expected_checkpoint, Mapping) or not {
        "bookId", "contentVersion", "currentSceneId", "terminal"
    }.issubset(expected_checkpoint):
        raise AttributionUnproven("incomplete expected checkpoint")
    if not isinstance(projection["checkpoint"], Mapping):
        raise AttributionUnproven("invalid projected checkpoint")
    filt = {"_id": ledger_id, "progressionRevision": base,
            "checkpoint": dict(expected_checkpoint),
            "appliedEventIds": {"$type": "object"},
            f"appliedEventIds.{target}": {"$exists": False},
            "mergedInto": {"$exists": False}, "fencedAt": {"$exists": False},
            "claimedBy": {"$exists": False}}
    if base > 0:
        # A foreign revision without its predecessor marker cannot be extended
        # into an apparently continuous, trusted progression history.
        filt[f"appliedEventIds.{base}"] = {"$type": "string", "$ne": ""}
    updated = await ledgers.find_one_and_update(
        filt,
        {"$set": {**dict(projection), "progressionRevision": target,
                  f"appliedEventIds.{target}": event_id}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    if updated is None:
        raise AttributionUnproven("attributed ledger CAS did not match")
    require_event_attribution(updated, event)
    return updated
