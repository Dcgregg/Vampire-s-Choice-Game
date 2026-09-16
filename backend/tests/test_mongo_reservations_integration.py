"""Real MongoDB smoke tests; TEST_MONGO_URI must point to a disposable DB.

These do not prove crash safety or production readiness. No production URI is read.
"""
import asyncio
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from progression.mongo_reservations import MongoReservationStore, ProgressionConflict


@pytest_asyncio.fixture
async def mongo_store():
    uri = os.environ.get("TEST_MONGO_URI")
    if not uri:
        pytest.skip("TEST_MONGO_URI not set: no disposable MongoDB")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    database = client[f"phase6b_ci_{uuid4().hex}"]
    try:
        await client.admin.command("ping")
        store = MongoReservationStore(database.ledgers, database.progression_events)
        await store.ensure_indexes()
        yield store
    finally:
        await client.drop_database(database.name)
        client.close()


@pytest.mark.asyncio
async def test_one_target_revision_has_one_winner(mongo_store):
    store = mongo_store
    ledger_id = uuid4().hex
    await store.ledgers.insert_one({"_id": ledger_id, "ownerType": "anon",
                                    "ownerId": uuid4().hex, "progressionRevision": 0})
    async def attempt(event_id):
        try:
            return await store.reserve(ledger_id=ledger_id, event_id=event_id,
                                       payload_hash=event_id, base_revision=0, awards={})
        except ProgressionConflict:
            return None
    results = await asyncio.gather(attempt("one"), attempt("two"))
    assert sum(event is not None and event.get("status") == "committing" for event in results) == 1
    assert await store.events.count_documents({"ledgerId": ledger_id, "targetRevision": 1}) == 1


@pytest.mark.asyncio
async def test_commit_and_finalise_are_idempotent(mongo_store):
    store = mongo_store
    ledger_id = uuid4().hex
    checkpoint = {"bookId": "book1", "currentSceneId": "start", "terminal": False}
    await store.ledgers.insert_one({"_id": ledger_id, "ownerType": "anon", "ownerId": uuid4().hex,
                                    "progressionRevision": 0, "checkpoint": checkpoint,
                                    "coins": {"confirmed": 250}, "achievements": {}, "derived": {}})
    event = await store.reserve(ledger_id=ledger_id, event_id="once", payload_hash="digest",
                                base_revision=0, awards={"coins": 10})
    projection = {"coins": {"confirmed": 260}, "achievements": {}, "derived": {},
                  "checkpoint": {"bookId": "book1", "currentSceneId": "next", "terminal": False}}
    first = await store.commit(event=event, lease_owner=event["leaseOwner"],
                               next_projection=projection, expected_checkpoint=checkpoint)
    assert first["progressionRevision"] == 1
    applied = await store.finalise(event=event, payload_hash="digest")
    assert applied["status"] == "applied"
    assert (await store.ledgers.find_one({"_id": ledger_id}))["coins"]["confirmed"] == 260
    assert (await store.events.count_documents({"ledgerId": ledger_id, "eventId": "once"})) == 1
    repeated = await store.reserve(ledger_id=ledger_id, event_id="once", payload_hash="digest",
                                   base_revision=0, awards={"coins": 10})
    assert repeated["status"] == "applied"
