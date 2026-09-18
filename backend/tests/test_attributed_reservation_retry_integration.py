"""Retry intent regressions for the inert attributed adapter; disposable MongoDB only."""
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from progression.attributed_mongo_reservations import AttributedMongoReservationStore
from progression.mongo_reservations import ReservationInvariantError


@pytest_asyncio.fixture
async def case():
    uri = os.environ.get("TEST_MONGO_URI")
    if not uri:
        pytest.skip("TEST_MONGO_URI required; never use production MongoDB")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    db = client[f"p6b_retry_intent_{uuid4().hex}"]
    try:
        await client.admin.command("ping")
        store = AttributedMongoReservationStore(db.ledgers, db.events)
        await store.ensure_indexes()
        ledger_id = uuid4().hex
        owner_id = uuid4().hex
        checkpoint = {"bookId": "book1", "contentVersion": 1,
                      "currentSceneId": "start", "terminal": False}
        projection = {"coins": {"confirmed": 10}, "achievements": {},
                      "derived": {}, "checkpoint": {**checkpoint, "currentSceneId": "next"}}
        await db.ledgers.insert_one({
            "_id": ledger_id, "ownerType": "account", "ownerId": owner_id,
            "progressionRevision": 0, "checkpoint": checkpoint,
            "appliedEventIds": {}, "coins": {"confirmed": 0},
            "achievements": {}, "derived": {},
        })
        event_id = str(uuid4())
        args = dict(ledger_id=ledger_id, event_id=event_id, payload_hash="digest",
                    base_revision=0, awards={"coins": 10},
                    next_projection=projection, expected_checkpoint=checkpoint,
                    expected_owner_type="account", expected_owner_id=owner_id)
        event = await store.reserve(**args)
        yield store, args, event
    finally:
        await client.drop_database(db.name)
        client.close()


@pytest.mark.asyncio
async def test_identical_retry_returns_original_reservation(case):
    store, args, event = case
    retried = await store.reserve(**args)
    assert retried["_id"] == event["_id"]
    assert retried["leaseOwner"] == event["leaseOwner"]


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [
    "awards", "next_projection", "expected_checkpoint", "expected_owner_id",
])
async def test_changed_retry_intent_is_rejected_without_rewriting_reservation(case, changed):
    store, args, event = case
    retry = dict(args)
    if changed == "awards":
        retry["awards"] = {"coins": 999}
    elif changed == "next_projection":
        retry["next_projection"] = {**args["next_projection"], "coins": {"confirmed": 999}}
    elif changed == "expected_checkpoint":
        retry["expected_checkpoint"] = {**args["expected_checkpoint"], "contentVersion": 2}
    else:
        retry["expected_owner_id"] = "different-account"
    expected_error = ("event_id_owner_mismatch" if changed == "expected_owner_id"
                      else "event_id_reserved_intent_mismatch")
    with pytest.raises(ReservationInvariantError, match=expected_error):
        await store.reserve(**retry)
    persisted = await store.events.find_one({"_id": event["_id"]})
    assert persisted["awards"] == args["awards"]
    assert persisted["nextProjection"] == args["next_projection"]
    assert persisted["expectedCheckpoint"] == args["expected_checkpoint"]
    assert persisted["expectedOwnerType"] == "account"
    assert persisted["expectedOwnerId"] == args["expected_owner_id"]
    assert persisted["status"] == "committing"
    assert (await store.ledgers.find_one({"_id": event["ledgerId"]}))["coins"]["confirmed"] == 0
