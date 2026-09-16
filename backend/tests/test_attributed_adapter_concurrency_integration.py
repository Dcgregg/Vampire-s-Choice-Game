"""Concurrency regressions for the inert attributed adapter; disposable MongoDB only."""
import asyncio
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from progression.attribution import AttributionUnproven
from progression.attributed_mongo_reservations import AttributedMongoReservationStore
from progression.mongo_reservations import ReservationBusy


@pytest_asyncio.fixture
async def case():
    uri = os.environ.get("TEST_MONGO_URI")
    if not uri:
        pytest.skip("TEST_MONGO_URI required; never use production MongoDB")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    db = client[f"phase6b_attributed_concurrency_{uuid4().hex}"]
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


@pytest.mark.asyncio
async def test_simultaneous_same_event_commits_never_double_grant(case):
    store, event = case
    results = await asyncio.gather(
        store.commit(event=event, lease_owner=event["leaseOwner"]),
        store.commit(event=event, lease_owner=event["leaseOwner"]),
        return_exceptions=True,
    )
    assert any(isinstance(result, dict) for result in results)
    assert all(isinstance(result, dict) or isinstance(result, ReservationBusy)
               for result in results), results
    ledger = await store.ledgers.find_one({"_id": event["ledgerId"]})
    assert ledger["progressionRevision"] == 1
    assert ledger["coins"]["confirmed"] == 10
    assert ledger["appliedEventIds"] == {"1": event["eventId"]}
    applied = await store.finalise(event=event, payload_hash="digest")
    assert applied["status"] == "applied"
    assert (await store.recover(applied))["resultRevision"] == 1


@pytest.mark.asyncio
async def test_foreign_revision_after_reservation_never_becomes_our_award(case):
    store, event = case
    await store.ledgers.update_one(
        {"_id": event["ledgerId"], "progressionRevision": 0},
        {"$set": {"progressionRevision": 1, "appliedEventIds.1": "foreign"}},
    )
    results = await asyncio.gather(
        store.commit(event=event, lease_owner=event["leaseOwner"]),
        store.recover(event), return_exceptions=True,
    )
    assert all(isinstance(result, AttributionUnproven) for result in results), results
    ledger = await store.ledgers.find_one({"_id": event["ledgerId"]})
    assert ledger["coins"]["confirmed"] == 0
    assert ledger["appliedEventIds"] == {"1": "foreign"}
    assert (await store.events.find_one({"_id": event["_id"]}))["status"] == "committing"
