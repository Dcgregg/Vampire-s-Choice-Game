"""Fault and concurrency checks against disposable real MongoDB.

Run with TEST_MONGO_URI; no production database should ever be used.
"""
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
        pytest.skip("TEST_MONGO_URI not set")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    database = client[f"phase6b_faults_{uuid4().hex}"]
    try:
        await client.admin.command("ping")
        instance = MongoReservationStore(database.ledgers, database.progression_events)
        await instance.ensure_indexes()
        yield instance
    finally:
        await client.drop_database(database.name)
        client.close()


def checkpoint(scene):
    return {"bookId": "book1", "currentSceneId": scene, "terminal": False}


def projection(scene, coins):
    return {"coins": {"confirmed": coins}, "achievements": {}, "derived": {},
            "checkpoint": checkpoint(scene)}


async def seed(store):
    ledger_id = uuid4().hex
    await store.ledgers.insert_one({"_id": ledger_id, "ownerType": "anon", "ownerId": uuid4().hex,
                                    "progressionRevision": 0, "checkpoint": checkpoint("start"),
                                    "coins": {"confirmed": 250}, "achievements": {}, "derived": {}})
    return ledger_id


async def reserve(store, ledger_id, event_id, base, start, end, coins):
    return await store.reserve(ledger_id=ledger_id, event_id=event_id, payload_hash=event_id,
                               base_revision=base, awards={"coins": 10},
                               next_projection=projection(end, coins), expected_checkpoint=checkpoint(start))


@pytest.mark.asyncio
async def test_expired_owner_cannot_commit_after_lease_is_stolen(store):
    ledger_id = await seed(store)
    original = await reserve(store, ledger_id, "first", 0, "start", "next", 260)
    await store.events.update_one({"_id": original["_id"]}, {"$set": {"leaseUntil": original["createdAt"]}})
    replacement = await store.acquire(original)
    with pytest.raises(ReservationBusy):
        await store.commit(event=original, lease_owner=original["leaseOwner"])
    await store.commit(event=replacement, lease_owner=replacement["leaseOwner"])
    await store.finalise(event=replacement, payload_hash="first")
    ledger = await store.ledgers.find_one({"_id": ledger_id})
    assert ledger["progressionRevision"] == 1
    assert ledger["coins"]["confirmed"] == 260


@pytest.mark.asyncio
async def test_two_recovery_workers_cannot_double_apply(store):
    ledger_id = await seed(store)
    event = await reserve(store, ledger_id, "race", 0, "start", "next", 260)
    await store.events.update_one({"_id": event["_id"]}, {"$set": {"leaseUntil": event["createdAt"]}})
    results = await asyncio.gather(store.recover(event), store.recover(event), return_exceptions=True)
    assert any(isinstance(result, dict) and result["status"] == "applied" for result in results)
    assert all(isinstance(result, dict) or isinstance(result, ReservationBusy) for result in results)
    ledger = await store.ledgers.find_one({"_id": ledger_id})
    assert ledger["progressionRevision"] == 1
    assert ledger["coins"]["confirmed"] == 260
    assert await store.events.count_documents({"ledgerId": ledger_id, "targetRevision": 1}) == 1


@pytest.mark.asyncio
async def test_recovery_of_old_event_after_later_event_preserves_later_state(store):
    ledger_id = await seed(store)
    first = await reserve(store, ledger_id, "first", 0, "start", "middle", 260)
    await store.commit(event=first, lease_owner=first["leaseOwner"])
    # Simulate a crash after ledger CAS but before finalising the first event.
    second = await reserve(store, ledger_id, "second", 1, "middle", "end", 270)
    await store.commit(event=second, lease_owner=second["leaseOwner"])
    await store.finalise(event=second, payload_hash="second")
    recovered = await store.recover(first)
    assert recovered["status"] == "applied"
    ledger = await store.ledgers.find_one({"_id": ledger_id})
    assert ledger["progressionRevision"] == 2
    assert ledger["coins"]["confirmed"] == 270
    assert ledger["checkpoint"] == checkpoint("end")
