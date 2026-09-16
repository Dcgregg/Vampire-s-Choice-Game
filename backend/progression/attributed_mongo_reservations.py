"""INERT attributed reservation adapter; not registered on any live route.

Only trusted callers may supply projections. This implementation requires clean
attribution-aware ledgers and an exclusive server-side ledger writer before use.
Existing ledgers are never silently upgraded or trusted.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from pymongo import ReturnDocument
from pymongo.errors import OperationFailure

from .attribution import AttributionUnproven, require_event_attribution
from .attributed_finalisation import finalise_attributed_event
from .attributed_ledger_write import write_attributed_revision
from .mongo_reservations import (
    MongoReservationStore, ProgressionConflict, ReservationBusy,
    ReservationInvariantError,
)


class AttributedMongoReservationStore(MongoReservationStore):
    """Opt-in inert adapter: never infer event authorship from revision alone."""

    async def commit(self, *, event: Mapping[str, Any], lease_owner: str,
                     next_projection: Mapping[str, Any] | None = None,
                     expected_checkpoint: Mapping[str, Any] | None = None) -> dict:
        if event.get("status") != "committing" or event.get("leaseOwner") != lease_owner:
            raise ReservationBusy("not the reservation owner")
        base, target = event.get("baseRevision"), event.get("targetRevision")
        if type(base) is not int or base < 0 or type(target) is not int or target != base + 1:
            raise ReservationInvariantError("invalid revision reservation")
        client = self.events.database.client
        async with await client.start_session() as session:
            try:
                async with session.start_transaction():
                    active = await self.events.find_one(
                        {"_id": event["_id"], "status": "committing",
                         "leaseOwner": lease_owner,
                         "leaseUntil": {"$gt": datetime.now(timezone.utc)}},
                        session=session,
                    )
                    if active is None:
                        raise ReservationBusy("lease expired or ownership changed")
                    if any(active.get(key) != event.get(key) for key in (
                        "ledgerId", "eventId", "payloadHash", "baseRevision", "targetRevision"
                    )):
                        raise ReservationInvariantError("persisted event identity changed")
                    projection, checkpoint = active.get("nextProjection"), active.get("expectedCheckpoint")
                    if projection is None or checkpoint is None:
                        raise ReservationInvariantError("reservation has no durable projection; cannot commit")
                    if next_projection is not None and dict(next_projection) != projection:
                        raise ReservationInvariantError("caller projection differs from reserved projection")
                    if expected_checkpoint is not None and dict(expected_checkpoint) != checkpoint:
                        raise ReservationInvariantError("caller checkpoint differs from reserved checkpoint")
                    fenced = await self.events.find_one_and_update(
                        {"_id": active["_id"], "status": "committing",
                         "leaseOwner": lease_owner,
                         "leaseUntil": {"$gt": datetime.now(timezone.utc)}},
                        {"$inc": {"commitFence": 1}},
                        return_document=ReturnDocument.AFTER, session=session,
                    )
                    if fenced is None:
                        raise ReservationBusy("lease expired or ownership changed")
                    try:
                        return await write_attributed_revision(
                            self.ledgers, event=active, projection=projection,
                            expected_checkpoint=checkpoint, session=session,
                        )
                    except AttributionUnproven:
                        # A missed CAS is not proof of this event's commit. A
                        # matching retained marker can reconcile an ambiguous
                        # previous transaction, but a foreign revision cannot.
                        current = await self.ledgers.find_one(
                            {"_id": active["ledgerId"]}, session=session,
                        )
                        if current is None:
                            raise
                        require_event_attribution(current, active)
                        return current
            except OperationFailure as exc:
                if exc.has_error_label("TransientTransactionError") or exc.code == 112:
                    raise ReservationBusy("lease fencing transaction conflicted; reconcile before retry") from exc
                raise

    async def finalise(self, *, event: Mapping[str, Any], payload_hash: str) -> dict:
        return await finalise_attributed_event(
            self.ledgers, self.events, event=event, payload_hash=payload_hash,
        )

    async def recover(self, event: Mapping[str, Any]) -> dict:
        """Recover only with exact proof; never trust an applied status alone."""
        if event.get("status") == "applied":
            return await self.finalise(event=event, payload_hash=event["payloadHash"])
        if event.get("status") != "committing":
            raise ReservationInvariantError("cannot recover unreserved event")
        ledger = await self.ledgers.find_one({"_id": event["ledgerId"]})
        if ledger is None:
            raise ReservationInvariantError("ledger missing during recovery")
        revision = ledger.get("progressionRevision")
        if type(revision) is not int:
            raise AttributionUnproven("invalid ledger revision during recovery")
        if revision >= event["targetRevision"]:
            return await self.finalise(event=event, payload_hash=event["payloadHash"])
        if revision != event["baseRevision"]:
            raise ProgressionConflict("ledger moved unexpectedly during recovery")
        acquired = await self.acquire(event)
        await self.commit(event=acquired, lease_owner=acquired["leaseOwner"])
        return await self.finalise(event=acquired, payload_hash=acquired["payloadHash"])
