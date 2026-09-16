"""Executable blocker: foreign ledger writes must not finalise a reserved event.

These strict xfails document an existing vulnerability; they are NOT evidence of
safe attribution. Remove xfail only after the adapter writes and verifies
immutable revision attribution in the same transaction as the projection.
TEST_MONGO_URI must point to disposable MongoDB, never production.
"""
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from progression.mongo_reservations import MongoReservationStore, ReservationInvariantError
from progression.attribution import AttributionUnproven


@pytest_asyncio.fixture
async def store():
    uri = os.environ.get("TEST_MONGO_URI")
    if not uri:
        pytest.skip("TEST_MONGO_URI not set: no disposable MongoDB")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    database = client[f"phase6b_attribution_blocker_{uuid4().hex}"]
    try:
        await client.admin.command("ping")
        adapter = MongoReservationStore(database.ledgers, database.events)
        await adapter.ensure_indexes()
        yield adapter
    finally:
        await client.drop_database(database.name)
        client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("foreign_revision", [1, 4])
@pytest.mark.xfail(strict=True, reason="BLOCKER: finalise infers authorship from revision alone")
async def test_foreign_revision_must_not_finalise_reserved_event(store, foreign_revision):
    ledger_id = uuid4().hex
    checkpoint = {"bookId": "book1", "contentVersion": 1,
                  "currentSceneId": "start", "terminal": False}
    await store.ledgers.insert_one({"_id": ledger_id, "ownerType": "account",
                                    "ownerId": uuid4().hex, "progressionRevision": 0,
                                    "checkpoint": checkpoint, "coins": {"confirmed": 0},
                                    "achievements": {}, "derived": {}})
    event = await store.reserve(
        ledger_id=ledger_id, event_id=str(uuid4()), payload_hash="digest",
        base_revision=0, awards={"coins": 10}, expected_checkpoint=checkpoint,
        next_projection={"coins": {"confirmed": 10}, "achievements": {},
                         "derived": {}, "checkpoint": {**checkpoint, "currentSceneId": "next"}},
    )
    # Simulate an unreserved writer: revision advances without this event's award
    # or an immutable attribution marker. This must never be called applied.
    await store.ledgers.update_one({"_id": ledger_id},
                                   {"$set": {"progressionRevision": foreign_revision}})
    with pytest.raises((ReservationInvariantError, AttributionUnproven)):
        await store.finalise(event=event, payload_hash="digest")
    assert (await store.events.find_one({"_id": event["_id"]}))["status"] != "applied"
