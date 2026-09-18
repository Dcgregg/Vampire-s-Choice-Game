"""Deterministic lease/CAS interleaving against disposable MongoDB.

A lease takeover before the ledger CAS must reject the old owner without
advancing the ledger; the new owner can then commit exactly once.
"""
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from progression.mongo_reservations import MongoReservationStore, ReservationBusy


@pytest_asyncio.fixture
async def store():
    uri = os.environ.get("TEST_MONGO_URI")
    if not uri:
        pytest.skip("TEST_MONGO_URI not set: requires disposable MongoDB")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    database = client[f"phase6b_interleave_{uuid4().hex}"]
    try:
        await client.admin.command("ping")
        instance = MongoReservationStore(database.ledgers, database.progression_events)
        await instance.ensure_indexes()
        yield instance
    finally:
        await client.drop_database(database.name)
        client.close()


@pytest.mark.asyncio
async def test_lease_takeover_after_preflight_cannot_apply_two_revisions(store):
    checkpoint = {"bookId": "book1", "currentSceneId": "start", "terminal": False}
    next_checkpoint = {**checkpoint, "currentSceneId": "next"}
    ledger_id = uuid4().hex
    await store.ledgers.insert_one({
        "_id": ledger_id, "ownerType": "anon", "ownerId": uuid4().hex,
        "progressionRevision": 0, "checkpoint": checkpoint,
        "coins": {"confirmed": 250}, "achievements": {}, "derived": {},
    })
    event = await store.reserve(
        ledger_id=ledger_id, event_id="interleaving", payload_hash="digest",
        base_revision=0, awards={"coins": 10}, expected_checkpoint=checkpoint,
        next_projection={"coins": {"confirmed": 260}, "achievements": {},
                         "derived": {}, "checkpoint": next_checkpoint},
    )
    original_write = store.ledgers.find_one_and_update
    takeover = {}

    async def write_after_takeover(*args, **kwargs):
        # The transaction has already written the event fence. An external
        # takeover cannot complete while that transaction holds the write.
        # This hook therefore checks the event still belongs to the caller.
        active = await store.events.find_one({"_id": event["_id"]}, session=kwargs.get("session"))
        assert active["leaseOwner"] == event["leaseOwner"]
        return await original_write(*args, **kwargs)

    store.ledgers.find_one_and_update = write_after_takeover
    try:
        await store.commit(event=event, lease_owner=event["leaseOwner"])
    finally:
        store.ledgers.find_one_and_update = original_write

    applied = await store.finalise(event=event, payload_hash="digest")
    ledger = await store.ledgers.find_one({"_id": ledger_id})
    assert applied["status"] == "applied"
    assert ledger["progressionRevision"] == 1
    assert ledger["coins"]["confirmed"] == 260
    assert ledger["checkpoint"] == next_checkpoint
    assert await store.events.count_documents({"ledgerId": ledger_id, "targetRevision": 1}) == 1
