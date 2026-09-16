"""INERT attributed finalisation candidate; not wired into live routes.

Requires the sole ledger writer to retain revision attribution atomically with
its projection. This function cannot make an untrusted attribution history safe.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from pymongo import ReturnDocument
from pymongo.errors import OperationFailure

from .attribution import AttributionUnproven, require_event_attribution


def _require_applied_result(event: Mapping[str, Any]) -> None:
    """An applied status is not proof when its recorded result is inconsistent."""
    if (type(event.get("resultRevision")) is not int
            or event["resultRevision"] != event.get("targetRevision")):
        raise AttributionUnproven("applied event has inconsistent result revision")


async def finalise_attributed_event(
    ledgers: Any, events: Any, *, event: Mapping[str, Any], payload_hash: str,
) -> dict:
    """Finalise only while the event's exact ledger proof is transactionally fenced.

    A guarded same-value ledger write makes a concurrent ledger mutation conflict
    with this transaction, including a change to the attribution marker. This
    still requires an exclusive trusted ledger writer and immutable history.
    """
    if not isinstance(payload_hash, str) or not payload_hash or event.get("payloadHash") != payload_hash:
        raise AttributionUnproven("event payload mismatch")
    if event.get("status") not in ("committing", "applied"):
        raise AttributionUnproven("event is not a committed reservation")
    client = events.database.client
    async with await client.start_session() as session:
        try:
            async with session.start_transaction():
                persisted = await events.find_one({"_id": event.get("_id")}, session=session)
                if persisted is None or any(persisted.get(key) != event.get(key) for key in (
                    "ledgerId", "eventId", "payloadHash", "baseRevision", "targetRevision"
                )) or persisted.get("payloadHash") != payload_hash:
                    raise AttributionUnproven("persisted event identity differs")
                if persisted.get("status") not in ("committing", "applied"):
                    raise AttributionUnproven("persisted event is not committing or applied")
                ledger = await ledgers.find_one({"_id": persisted["ledgerId"]}, session=session)
                if ledger is None:
                    raise AttributionUnproven("ledger missing")
                require_event_attribution(ledger, persisted)
                target = str(persisted["targetRevision"])
                marker_path = f"appliedEventIds.{target}"
                # A read alone does not detect a proof mutation after the read.
                # The guarded write holds a document write conflict until commit.
                guarded = await ledgers.update_one(
                    {"_id": ledger["_id"], "progressionRevision": {"$gte": persisted["targetRevision"]},
                     marker_path: persisted["eventId"]},
                    {"$set": {marker_path: persisted["eventId"]}}, session=session,
                )
                if guarded.matched_count != 1:
                    raise AttributionUnproven("attribution changed during finalisation")
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
                    return_document=ReturnDocument.AFTER, session=session,
                )
                if result is None:
                    raise AttributionUnproven("event finalisation raced without matching proof")
                _require_applied_result(result)
                return result
        except OperationFailure as exc:
            if exc.has_error_label("TransientTransactionError") or exc.code == 112:
                raise AttributionUnproven("attribution finalisation transaction conflicted; retry") from exc
            raise
