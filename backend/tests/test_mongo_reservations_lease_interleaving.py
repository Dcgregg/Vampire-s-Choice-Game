"""Deterministic lease/CAS interleaving against disposable MongoDB.

This test establishes the current single-revision safety property; it does NOT
prove strict lease-owner fencing. That requires an atomic cross-document guard
(e.g. a MongoDB transaction) before enabling this adapter for live players.
"""
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from progression.mongo_reservations import MongoReservationStore


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
        # commit() already checked the original lease. Force expiry and transfer
        # ownership immediately before its ledger CAS, then let the old call run.
        await store.events.update_one(
            {"_id": event["_id"]},
            {"$set": {"leaseUntil": datetime.now(timezone.utc) - timedelta(seconds=1)}},
        )
        takeover["event"] = await store.acquire(event)
        return await original_write(*args, **kwargs)

    store.ledgers.find_one_and_update = write_after_takeover
    try:
        await store.commit(event=event, lease_owner=event["leaseOwner"])
    finally:
        store.ledgers.find_one_and_update = original_write

    # The old owner can currently write after losing the lease. This is a
    # documented limitation, not a claim that strict fencing is implemented.
    assert takeover["event"]["leaseOwner"] != event["leaseOwner"]
    await store.commit(event=takeover["event"], lease_owner=takeover["event"]["leaseOwner"])
    applied = await store.finalise(event=takeover["event"], payload_hash="digest")
    ledger = await store.ledgers.find_one({"_id": ledger_id})
    assert applied["status"] == "applied"
    assert ledger["progressionRevision"] == 1
    assert ledger["coins"]["confirmed"] == 260
    assert ledger["checkpoint"] == next_checkpoint
    assert await store.events.count_documents({"ledgerId": ledger_id, "targetRevision": 1}) == 1
