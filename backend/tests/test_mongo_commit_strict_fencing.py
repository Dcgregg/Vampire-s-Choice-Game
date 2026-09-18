"""Adapter-level strict fencing regression against disposable MongoDB.

The old owner must not advance the ledger if takeover occurs after its
preflight read. This test is intentionally red until commit() atomically
fences the reservation event and updates the ledger in one transaction.
"""
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from progression.mongo_reservations import MongoReservationStore, ReservationBusy


@pytest.mark.asyncio
async def test_old_owner_cannot_commit_after_takeover_between_preflight_and_ledger_write():
    uri = os.environ.get("TEST_MONGO_URI")
    if not uri:
        pytest.skip("TEST_MONGO_URI not set: disposable replica set required")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    database = client[f"phase6b_strict_fence_{uuid4().hex}"]
    store = MongoReservationStore(database.ledgers, database.progression_events)
    checkpoint = {"bookId": "book1", "currentSceneId": "start", "terminal": False}
    next_checkpoint = {**checkpoint, "currentSceneId": "next"}
    ledger_id = uuid4().hex
    try:
        await client.admin.command("ping")
        await store.ensure_indexes()
        await store.ledgers.insert_one({
            "_id": ledger_id, "ownerType": "anon", "ownerId": uuid4().hex,
            "progressionRevision": 0, "checkpoint": checkpoint,
            "coins": {"confirmed": 250}, "achievements": {}, "derived": {},
        })
        event = await store.reserve(
            ledger_id=ledger_id, event_id="strict-fence", payload_hash="digest",
            base_revision=0, awards={"coins": 10}, expected_checkpoint=checkpoint,
            next_projection={"coins": {"confirmed": 260}, "achievements": {},
                             "derived": {}, "checkpoint": next_checkpoint},
        )
        original_read = store.events.find_one
        takeover = {}

        async def read_then_takeover(*args, **kwargs):
            active = await original_read(*args, **kwargs)
            if active is not None and args and args[0].get("leaseOwner") == event["leaseOwner"]:
                await store.events.update_one(
                    {"_id": event["_id"], "leaseOwner": event["leaseOwner"]},
                    {"$set": {"leaseUntil": datetime.now(timezone.utc) - timedelta(seconds=1)}},
                )
                takeover["event"] = await store.acquire(event)
            return active

        store.events.find_one = read_then_takeover
        try:
            with pytest.raises(ReservationBusy):
                await store.commit(event=event, lease_owner=event["leaseOwner"])
        finally:
            store.events.find_one = original_read
        assert takeover["event"]["leaseOwner"] != event["leaseOwner"]
        ledger = await store.ledgers.find_one({"_id": ledger_id})
        assert ledger["progressionRevision"] == 0
        assert ledger["coins"]["confirmed"] == 250
        await store.commit(event=takeover["event"], lease_owner=takeover["event"]["leaseOwner"])
        ledger = await store.ledgers.find_one({"_id": ledger_id})
        assert ledger["progressionRevision"] == 1
        assert ledger["coins"]["confirmed"] == 260
    finally:
        await client.drop_database(database.name)
        client.close()
