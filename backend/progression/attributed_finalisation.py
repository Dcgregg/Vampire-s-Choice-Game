"""INERT attributed finalisation candidate; not wired into live routes or adapter.

Requires the sole ledger writer to retain revision attribution atomically with
its projection. This function cannot make an untrusted attribution history safe.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from pymongo import ReturnDocument

from .attribution import AttributionUnproven, require_event_attribution


def _require_applied_result(event: Mapping[str, Any]) -> None:
    """An applied status is not proof when its recorded result is inconsistent."""
    if (type(event.get("resultRevision")) is not int
            or event["resultRevision"] != event.get("targetRevision")):
        raise AttributionUnproven("applied event has inconsistent result revision")


async def finalise_attributed_event(
    ledgers: Any, events: Any, *, event: Mapping[str, Any], payload_hash: str,
) -> dict:
    """Only mark a reserved event applied after checking its exact ledger marker.

    A concurrent status change is reconciled against the persisted event; it
    cannot turn a different payload or revision into a successful retry.
    """
    if not isinstance(payload_hash, str) or not payload_hash or event.get("payloadHash") != payload_hash:
        raise AttributionUnproven("event payload mismatch")
    if event.get("status") not in ("committing", "applied"):
        raise AttributionUnproven("event is not a committed reservation")
    persisted = await events.find_one({"_id": event.get("_id")})
    if persisted is None or any(persisted.get(key) != event.get(key) for key in (
        "ledgerId", "eventId", "payloadHash", "baseRevision", "targetRevision"
    )) or persisted.get("payloadHash") != payload_hash:
        raise AttributionUnproven("persisted event identity differs")
    if persisted.get("status") not in ("committing", "applied"):
        raise AttributionUnproven("persisted event is not committing or applied")
    ledger = await ledgers.find_one({"_id": persisted["ledgerId"]})
    if ledger is None:
        raise AttributionUnproven("ledger missing")
    require_event_attribution(ledger, persisted)
    if persisted["status"] == "applied":
        _require_applied_result(persisted)
        return persisted
    result = await events.find_one_and_update(
        {"_id": persisted["_id"], "status": "committing",
         "ledgerId": persisted["ledgerId"], "eventId": persisted["eventId"],
         "payloadHash": payload_hash, "baseRevision": persisted["baseRevision"],
         "targetRevision": persisted["targetRevision"]},
        {"$set": {"status": "applied", "resultRevision": persisted["targetRevision"],
                  "appliedAt": datetime.now(timezone.utc)}},
        return_document=ReturnDocument.AFTER,
    )
    if result is not None:
        _require_applied_result(result)
        return result
    raced = await events.find_one({"_id": persisted["_id"]})
    if raced is None or raced.get("status") != "applied" or any(
        raced.get(key) != persisted.get(key) for key in (
            "ledgerId", "eventId", "payloadHash", "baseRevision", "targetRevision"
        )
    ):
        raise AttributionUnproven("event finalisation raced without matching proof")
    _require_applied_result(raced)
    return raced
