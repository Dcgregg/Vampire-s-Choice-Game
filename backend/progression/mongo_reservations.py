"""INERT Phase 6B Mongo persistence slice; not imported by the live API.

Caller must validate trusted content and compute the entire next ledger projection
before reserve(). Never accept client-supplied awards. The adapter owns only the
reservation/atomic-commit protocol, not game rules or identity resolution.

IMPORTANT: run ensure_indexes() before any writes, with majority write concern
on a replica set or acknowledged/journaled writes on standalone Mongo. The
revision attribution proof assumes durable writes and that NO OTHER code path
increments progressionRevision. Never delete reserved event documents.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from uuid import uuid4

from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from .reservations import Reservation, ReservationDecision, decide_retry


class ProgressionConflict(Exception):
    """Ledger moved or another event owns the requested revision."""


class ReservationBusy(Exception):
    """An existing worker has an unexpired lease; retry later."""


class ReservationInvariantError(Exception):
    """Persistence state cannot be safely reconciled; do not award."""


class MongoReservationStore:
    """Motor collections, supplied by caller; no global DB or route wiring."""

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
                      base_revision: int, awards: Mapping[str, Any]) -> dict:
        """Reserve base+1 exclusively. Caller has already validated at base.

        A duplicate ID never changes its payload. A different ID cannot take an
        occupied target revision. A collision leaves the losing event received,
        with no targetRevision, so it can be rejected/reconciled separately.
        """
        if base_revision < 0 or not event_id or not payload_hash:
            raise ValueError("invalid reservation input")
        now = datetime.now(timezone.utc)
        try:
            await self.events.insert_one({"ledgerId": ledger_id, "eventId": event_id,
                                          "payloadHash": payload_hash, "status": "received",
                                          "createdAt": now})
        except DuplicateKeyError:
            pass
        event = await self.events.find_one({"ledgerId": ledger_id, "eventId": event_id})
        if event is None:
            raise ReservationInvariantError("event claim missing after insert")
        if event["payloadHash"] != payload_hash:
            raise ReservationInvariantError("event_id_payload_mismatch")
        if event["status"] != "received":
            return event
        owner = uuid4().hex
        try:
            result = await self.events.find_one_and_update(
                {"_id": event["_id"], "status": "received", "targetRevision": {"$exists": False}},
                {"$set": {"status": "committing", "baseRevision": base_revision,
                          "targetRevision": base_revision + 1, "awards": dict(awards),
                          "leaseOwner": owner,
                          "leaseUntil": now + timedelta(seconds=self.lease_seconds)}},
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError as exc:
            # Only this event's received claim remains; NEVER clear the winner.
            raise ProgressionConflict("target revision already reserved") from exc
        if result is None:
            return await self.events.find_one({"_id": event["_id"]})
        return result

    async def acquire(self, event: Mapping[str, Any]) -> dict:
        """Take over only an expired lease; otherwise only its owner may commit.

        Lease ownership serialises workers, but the ledger revision CAS is the
        final exactly-once guard even if a paused worker resumes after expiry.
        """
        if event.get("status") != "committing":
            raise ReservationInvariantError("cannot acquire noncommitting event")
        now = datetime.now(timezone.utc)
        token = uuid4().hex
        claimed = await self.events.find_one_and_update(
            {"_id": event["_id"], "status": "committing",
             "leaseUntil": {"$lte": now}},
            {"$set": {"leaseOwner": token,
                      "leaseUntil": now + timedelta(seconds=self.lease_seconds)}},
            return_document=ReturnDocument.AFTER,
        )
        if claimed is None:
            raise ReservationBusy("reservation lease still active or already resolved")
        return claimed

    async def commit(self, *, event: Mapping[str, Any], lease_owner: str,
                     next_projection: Mapping[str, Any],
                     expected_checkpoint: Mapping[str, Any]) -> dict:
        """Only the conditional single-ledger write grants rewards.

        next_projection MUST be server-derived and contain the complete updated
        coins, achievements, derived, checkpoint and lifecycle guards. No
        database mutation happens if revision/checkpoint/lease checks fail.
        A caller MUST NOT recompute a pending event against a newer ledger.
        """
        if event.get("status") != "committing" or event.get("leaseOwner") != lease_owner:
            raise ReservationBusy("not the reservation owner")
        base, target = event.get("baseRevision"), event.get("targetRevision")
        if not isinstance(base, int) or target != base + 1:
            raise ReservationInvariantError("invalid revision reservation")
        # Re-read ownership before committing. A lease can still expire between
        # this read and ledger CAS; revision CAS makes a second commit impossible.
        active = await self.events.find_one({"_id": event["_id"], "status": "committing",
                                             "leaseOwner": lease_owner,
                                             "leaseUntil": {"$gt": datetime.now(timezone.utc)}})
        if active is None:
            raise ReservationBusy("lease expired or ownership changed")
        allowed = {"coins", "achievements", "derived", "checkpoint", "lifecycleApplied", "openingGranted"}
        if set(next_projection) - allowed or not {"coins", "achievements", "derived", "checkpoint"}.issubset(next_projection):
            raise ValueError("invalid server projection fields")
        filt = {"_id": event["ledgerId"], "progressionRevision": base,
                "checkpoint.bookId": expected_checkpoint["bookId"],
                "checkpoint.currentSceneId": expected_checkpoint["currentSceneId"],
                "checkpoint.terminal": False,
                "mergedInto": {"$exists": False}, "fencedAt": {"$exists": False}}
        updated = await self.ledgers.find_one_and_update(
            filt, {"$set": {**dict(next_projection), "progressionRevision": target}},
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            current = await self.ledgers.find_one({"_id": event["ledgerId"]})
            if current is None or current.get("progressionRevision", -1) < target:
                raise ProgressionConflict("ledger checkpoint or revision changed")
            # Unique reservation + sole ledger writer proves attribution.
            return current
        return updated

    async def finalise(self, *, event: Mapping[str, Any], payload_hash: str) -> dict:
        """Finalise only after ledger revision proves this event committed."""
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
