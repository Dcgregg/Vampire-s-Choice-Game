"""Disposable-MongoDB concurrency checks for the inert Phase 6B adapter."""
import asyncio
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from progression.mongo_reservations import MongoReservationStore, ReservationBusy


@pytest_asyncio.fixture
async def store():
    uri = os.environ.get("TEST_MONGO_URI")
    if not uri:
        pytest.skip("TEST_MONGO_URI not set: no disposable MongoDB")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    database = client[f"phase6b_recovery_{uuid4().hex}"]
    try:
        await client.admin.command("ping")
        adapter = MongoReservationStore(database.ledgers, database.progression_events)
        await adapter.ensure_indexes()
        yield adapter
    finally:
        await client.drop_database(database.name)
        client.close()


async def reserve_expired(store):
    ledger_id = uuid4().hex
    checkpoint = {"bookId": "book1", "currentSceneId": "start", "terminal": False}
    await store.ledgers.insert_one({"_id": ledger_id, "ownerType": "anon", "ownerId": uuid4().hex,
                                    "progressionRevision": 0, "checkpoint": checkpoint,
                                    "coins": {"confirmed": 250}, "achievements": {}, "derived": {}})
    projection = {"coins": {"confirmed": 260}, "achievements": {}, "derived": {},
                  "checkpoint": {"bookId": "book1", "currentSceneId": "next", "terminal": False}}
    event = await store.reserve(ledger_id=ledger_id, event_id="recovery-race", payload_hash="digest",
                                base_revision=0, awards={"coins": 10},
                                next_projection=projection, expected_checkpoint=checkpoint)
    await store.events.update_one({"_id": event["_id"]}, {"$set": {"leaseUntil": event["createdAt"]}})
    return ledger_id, event


@pytest.mark.asyncio
async def test_two_recovery_workers_apply_exactly_once(store):
    ledger_id, event = await reserve_expired(store)
    outcomes = await asyncio.gather(store.recover(event), store.recover(event), return_exceptions=True)
    assert all(isinstance(outcome, (dict, ReservationBusy)) for outcome in outcomes), outcomes
    assert any(isinstance(outcome, dict) and outcome["status"] == "applied" for outcome in outcomes)
    ledger = await store.ledgers.find_one({"_id": ledger_id})
    assert ledger["progressionRevision"] == 1
    assert ledger["coins"]["confirmed"] == 260
    assert await store.events.count_documents({"ledgerId": ledger_id, "status": "applied"}) == 1
    assert (await store.recover(event))["status"] == "applied"


@pytest.mark.asyncio
async def test_expired_original_owner_cannot_commit_after_lease_takeover(store):
    ledger_id, event = await reserve_expired(store)
    acquired = await store.acquire(event)
    assert acquired["leaseOwner"] != event["leaseOwner"]
    with pytest.raises(ReservationBusy):
        await store.commit(event=event, lease_owner=event["leaseOwner"])
    assert (await store.ledgers.find_one({"_id": ledger_id}))["progressionRevision"] == 0
    await store.commit(event=acquired, lease_owner=acquired["leaseOwner"])
    assert (await store.finalise(event=acquired, payload_hash="digest"))["status"] == "applied"
    assert (await store.ledgers.find_one({"_id": ledger_id}))["coins"]["confirmed"] == 260
