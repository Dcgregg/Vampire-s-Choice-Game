"""INERT Phase 6B Mongo persistence adapter; not wired to the live API.

Only a trusted server validator may call reserve. Indexes must exist before
writes, writes must be durable, and this adapter must be the sole revision
writer. Never delete reserved events: revision attribution depends on them.
Commit requires a MongoDB replica set with transaction support.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from uuid import uuid4

from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, OperationFailure

from .reservations import Reservation, ReservationDecision, decide_retry


class ProgressionConflict(Exception):
    """Ledger changed or a competing event reserved this revision."""


class ReservationBusy(Exception):
    """A worker holds the lease or the lease has changed."""


class ReservationInvariantError(Exception):
    """Persistence cannot be reconciled safely; do not grant awards."""


_PROJECTION_FIELDS = frozenset({"coins", "achievements", "derived", "checkpoint", "lifecycleApplied", "openingGranted"})
_REQUIRED_FIELDS = frozenset({"coins", "achievements", "derived", "checkpoint"})


class MongoReservationStore:
    def __init__(self, ledgers: Any, events: Any, *, lease_seconds: int = 60):
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        self.ledgers, self.events, self.lease_seconds = ledgers, events, lease_seconds

    async def ensure_indexes(self) -> None:
        await self.ledgers.create_index([("ownerType", ASCENDING), ("ownerId", ASCENDING)], unique=True)
        await self.events.create_index([("ledgerId", ASCENDING), ("eventId", ASCENDING)], unique=True)
        await self.events.create_index(
            [("ledgerId", ASCENDING), ("targetRevision", ASCENDING)], unique=True,
            partialFilterExpression={"targetRevision": {"$exists": True}},
        )

    async def reserve(self, *, ledger_id: Any, event_id: str, payload_hash: str,
                      base_revision: int, awards: Mapping[str, Any],
                      next_projection: Mapping[str, Any] | None = None,
                      expected_checkpoint: Mapping[str, Any] | None = None,
                      expected_owner_type: str | None = None,
                      expected_owner_id: str | None = None) -> dict:
        """Claim an ID, then exclusively reserve base+1 with a durable result.

        A caller may omit projection/checkpoint for reservation-only tests, but
        such a reservation CANNOT commit or recover. Production callers must
        provide both from trusted validation against the exact base ledger.
        """
        if isinstance(base_revision, bool) or not isinstance(base_revision, int) or base_revision < 0 or not event_id or not payload_hash:
            raise ValueError("invalid reservation input")
        if (next_projection is None) != (expected_checkpoint is None):
            raise ValueError("projection and checkpoint must be provided together")
        if (expected_owner_type is None) != (expected_owner_id is None):
            raise ValueError("owner type and ID must be provided together")
        if expected_owner_type is not None and (
            not isinstance(expected_owner_type, str) or not expected_owner_type
            or not isinstance(expected_owner_id, str) or not expected_owner_id
        ):
            raise ValueError("invalid expected owner")
        if next_projection is not None:
            if set(next_projection) - _PROJECTION_FIELDS or not _REQUIRED_FIELDS.issubset(next_projection):
                raise ValueError("invalid server projection fields")
            if not {"bookId", "currentSceneId", "terminal"}.issubset(expected_checkpoint):
                raise ValueError("incomplete expected checkpoint")
        now = datetime.now(timezone.utc)
        try:
            claimed = {"ledgerId": ledger_id, "eventId": event_id,
                       "payloadHash": payload_hash, "status": "received",
                       "createdAt": now}
            if expected_owner_type is not None:
                claimed["expectedOwnerType"] = expected_owner_type
                claimed["expectedOwnerId"] = expected_owner_id
            await self.events.insert_one(claimed)
        except DuplicateKeyError:
            pass
        event = await self.events.find_one({"ledgerId": ledger_id, "eventId": event_id})
        if event is None:
            raise ReservationInvariantError("event claim missing after insert")
        if event["payloadHash"] != payload_hash:
            raise ReservationInvariantError("event_id_payload_mismatch")
        if expected_owner_type is not None and (
            event.get("expectedOwnerType") != expected_owner_type
            or event.get("expectedOwnerId") != expected_owner_id
        ):
            raise ReservationInvariantError("event_id_owner_mismatch")
        if event["status"] != "received":
            if event.get("baseRevision") != base_revision:
                raise ReservationInvariantError("event_id_base_revision_mismatch")
            return event
        ledger_query = {"_id": ledger_id}
        if expected_owner_type is not None:
            ledger_query.update({"ownerType": expected_owner_type,
                                 "ownerId": expected_owner_id})
        ledger = await self.ledgers.find_one(ledger_query)
        if ledger is None or ledger.get("progressionRevision") != base_revision:
            raise ProgressionConflict("ledger revision changed before reservation")
        if expected_checkpoint is not None and ledger.get("checkpoint") != dict(expected_checkpoint):
            raise ProgressionConflict("ledger checkpoint changed before reservation")
        if ledger.get("mergedInto") is not None or ledger.get("fencedAt") is not None or ledger.get("claimedBy") is not None:
            raise ProgressionConflict("ledger is fenced or claimed")
        owner = uuid4().hex
        fields = {"status": "committing", "baseRevision": base_revision,
                  "targetRevision": base_revision + 1, "awards": dict(awards),
                  "leaseOwner": owner, "leaseUntil": now + timedelta(seconds=self.lease_seconds)}
        if next_projection is not None:
            fields["nextProjection"] = dict(next_projection)
            fields["expectedCheckpoint"] = dict(expected_checkpoint)
        try:
            result = await self.events.find_one_and_update(
                {"_id": event["_id"], "status": "received", "targetRevision": {"$exists": False}},
                {"$set": fields}, return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError as exc:
            raise ProgressionConflict("target revision already reserved") from exc
        if result is None:
            result = await self.events.find_one({"_id": event["_id"]})
        if result is None:
            raise ReservationInvariantError("reservation vanished")
        if result.get("payloadHash") != payload_hash or result.get("baseRevision") != base_revision:
            raise ReservationInvariantError("event changed during reservation")
        return result

    async def acquire(self, event: Mapping[str, Any]) -> dict:
        if event.get("status") != "committing":
            raise ReservationInvariantError("cannot acquire noncommitting event")
        now = datetime.now(timezone.utc)
        claimed = await self.events.find_one_and_update(
            {"_id": event["_id"], "status": "committing", "leaseUntil": {"$lte": now}},
            {"$set": {"leaseOwner": uuid4().hex,
                      "leaseUntil": now + timedelta(seconds=self.lease_seconds)}},
            return_document=ReturnDocument.AFTER,
        )
        if claimed is None:
            raise ReservationBusy("reservation lease still active or already resolved")
        return claimed

    async def commit(self, *, event: Mapping[str, Any], lease_owner: str,
                     next_projection: Mapping[str, Any] | None = None,
                     expected_checkpoint: Mapping[str, Any] | None = None) -> dict:
        """Atomically fence the lease owner and CAS the immutable projection.

        A conditional event *write* and ledger CAS share one transaction. A
        takeover that commits first invalidates this transaction's event write;
        a takeover that races later conflicts with the transaction's write.
        No transaction errors are silently retried: callers must reconcile
        ambiguous results via durable event/ledger state before any retry.
        """
        if event.get("status") != "committing" or event.get("leaseOwner") != lease_owner:
            raise ReservationBusy("not the reservation owner")
        base, target = event.get("baseRevision"), event.get("targetRevision")
        if isinstance(base, bool) or not isinstance(base, int) or target != base + 1:
            raise ReservationInvariantError("invalid revision reservation")
        # Both collections must belong to the same MongoDB client/database.
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
                    projection, checkpoint = active.get("nextProjection"), active.get("expectedCheckpoint")
                    if projection is None or checkpoint is None:
                        raise ReservationInvariantError("reservation has no durable projection; cannot commit")
                    if next_projection is not None and dict(next_projection) != projection:
                        raise ReservationInvariantError("caller projection differs from reserved projection")
                    if expected_checkpoint is not None and dict(expected_checkpoint) != checkpoint:
                        raise ReservationInvariantError("caller checkpoint differs from reserved checkpoint")
                    if set(projection) - _PROJECTION_FIELDS or not _REQUIRED_FIELDS.issubset(projection):
                        raise ReservationInvariantError("invalid persisted projection")
                    if not {"bookId", "currentSceneId", "terminal"}.issubset(checkpoint):
                        raise ReservationInvariantError("invalid persisted checkpoint")
                    # This is deliberately a WRITE, not a preflight-only read.
                    # A concurrent acquire() writes this same document.
                    fenced = await self.events.find_one_and_update(
                        {"_id": active["_id"], "status": "committing",
                         "leaseOwner": lease_owner,
                         "leaseUntil": {"$gt": datetime.now(timezone.utc)}},
                        {"$inc": {"commitFence": 1}},
                        return_document=ReturnDocument.AFTER, session=session,
                    )
                    if fenced is None:
                        raise ReservationBusy("lease expired or ownership changed")
                    filt = {"_id": active["ledgerId"], "progressionRevision": base,
                            # Compare the complete pinned checkpoint, not just
                            # book/scene/terminal: a version change must fence.
                            "checkpoint": dict(checkpoint),
                            "mergedInto": {"$exists": False}, "fencedAt": {"$exists": False},
                            "claimedBy": {"$exists": False}}
                    updated = await self.ledgers.find_one_and_update(
                        filt, {"$set": {**projection, "progressionRevision": target}},
                        return_document=ReturnDocument.AFTER, session=session,
                    )
                    if updated is None:
                        current = await self.ledgers.find_one({"_id": active["ledgerId"]}, session=session)
                        if current is None or current.get("progressionRevision", -1) < target:
                            raise ProgressionConflict("ledger checkpoint or revision changed")
                        return current
                    return updated
            except OperationFailure as exc:
                if exc.has_error_label("TransientTransactionError") or exc.code == 112:
                    raise ReservationBusy("lease fencing transaction conflicted; reconcile before retry") from exc
                raise

    async def finalise(self, *, event: Mapping[str, Any], payload_hash: str) -> dict:
        if event.get("payloadHash") != payload_hash:
            raise ReservationInvariantError("event_id_payload_mismatch")
        ledger = await self.ledgers.find_one({"_id": event["ledgerId"]})
        if ledger is None:
            raise ReservationInvariantError("ledger missing")
        decision = decide_retry(
            Reservation(event["eventId"], event["payloadHash"], event["status"],
                        event.get("baseRevision"), event.get("targetRevision")),
            payload_hash, ledger["progressionRevision"],
        )
        if decision == ReservationDecision.RETURN_APPLIED:
            return dict(event)
        if decision != ReservationDecision.FINALISE:
            raise ReservationInvariantError(f"cannot finalise: {decision.value}")
        result = await self.events.find_one_and_update(
            {"_id": event["_id"], "status": "committing", "payloadHash": payload_hash},
            {"$set": {"status": "applied", "resultRevision": event["targetRevision"],
                      "appliedAt": datetime.now(timezone.utc)}},
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            result = await self.events.find_one({"_id": event["_id"]})
            if result is None or result.get("status") != "applied":
                raise ReservationInvariantError("event finalisation raced unexpectedly")
        return result

    async def recover(self, event: Mapping[str, Any]) -> dict:
        """Complete an expired, fully validated reservation without recomputing.

        Safe to retry after an ambiguous ledger write or a crash between ledger
        CAS and event finalisation. Unvalidated legacy reservations fail closed.
        """
        if event.get("status") == "applied":
            return dict(event)
        if event.get("status") != "committing":
            raise ReservationInvariantError("cannot recover unreserved event")
        ledger = await self.ledgers.find_one({"_id": event["ledgerId"]})
        if ledger is None:
            raise ReservationInvariantError("ledger missing during recovery")
        if ledger.get("progressionRevision", -1) >= event["targetRevision"]:
            return await self.finalise(event=event, payload_hash=event["payloadHash"])
        if ledger.get("progressionRevision") != event["baseRevision"]:
            raise ProgressionConflict("ledger moved unexpectedly during recovery")
        acquired = await self.acquire(event)
        await self.commit(event=acquired, lease_owner=acquired["leaseOwner"])
        return await self.finalise(event=acquired, payload_hash=acquired["payloadHash"])
