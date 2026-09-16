"""Disposable-MongoDB lease failure regressions for the inert attributed adapter."""
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from progression.attributed_mongo_reservations import AttributedMongoReservationStore
from progression.mongo_reservations import ReservationBusy


@pytest_asyncio.fixture
async def case():
    uri = os.environ.get("TEST_MONGO_URI")
    if not uri:
        pytest.skip("TEST_MONGO_URI required; never run against production MongoDB")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    db = client[f"phase6b_attributed_lease_faults_{uuid4().hex}"]
    try:
        await client.admin.command("ping")
        store = AttributedMongoReservationStore(db.ledgers, db.events)
        await store.ensure_indexes()
        ledger_id = uuid4().hex
        checkpoint = {"bookId": "book1", "contentVersion": 1,
                      "currentSceneId": "start", "terminal": False}
        await db.ledgers.insert_one({
            "_id": ledger_id, "ownerType": "account", "ownerId": uuid4().hex,
            "progressionRevision": 0, "checkpoint": checkpoint,
            "appliedEventIds": {}, "coins": {"confirmed": 0},
            "achievements": {}, "derived": {},
        })
        event = await store.reserve(
            ledger_id=ledger_id, event_id=str(uuid4()), payload_hash="digest",
            base_revision=0, awards={"coins": 10},
            next_projection={"coins": {"confirmed": 10}, "achievements": {},
                             "derived": {}, "checkpoint": {**checkpoint, "currentSceneId": "next"}},
            expected_checkpoint=checkpoint,
        )
        yield store, event
    finally:
        await client.drop_database(db.name)
        client.close()


async def assert_no_commit(store, event, *, expected_owner):
    ledger = await store.ledgers.find_one({"_id": event["ledgerId"]})
    stored = await store.events.find_one({"_id": event["_id"]})
    assert ledger["progressionRevision"] == 0
    assert ledger["coins"]["confirmed"] == 0
    assert ledger["appliedEventIds"] == {}
    assert stored["status"] == "committing"
    assert stored["leaseOwner"] == expected_owner
    assert stored.get("commitFence", 0) == event.get("commitFence", 0)


@pytest.mark.asyncio
async def test_expired_lease_cannot_commit_or_advance_fence(case):
    store, event = case
    await store.events.update_one(
        {"_id": event["_id"]},
        {"$set": {"leaseUntil": datetime.now(timezone.utc) - timedelta(seconds=5)}},
    )
    with pytest.raises(ReservationBusy, match="lease expired"):
        await store.commit(event=event, lease_owner=event["leaseOwner"])
    await assert_no_commit(store, event, expected_owner=event["leaseOwner"])


@pytest.mark.asyncio
async def test_stolen_lease_cannot_commit_or_advance_fence(case):
    store, event = case
    await store.events.update_one(
        {"_id": event["_id"]},
        {"$set": {"leaseOwner": "replacement-worker",
                  "leaseUntil": datetime.now(timezone.utc) + timedelta(minutes=5)}},
    )
    with pytest.raises(ReservationBusy, match="ownership changed"):
        await store.commit(event=event, lease_owner=event["leaseOwner"])
    await assert_no_commit(store, event, expected_owner="replacement-worker")
