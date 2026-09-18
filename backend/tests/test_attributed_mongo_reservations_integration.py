"""End-to-end inert attributed adapter tests; TEST_MONGO_URI must be disposable."""
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from progression.attribution import AttributionUnproven
from progression.attributed_mongo_reservations import AttributedMongoReservationStore


def checkpoint():
    return {"bookId": "book1", "contentVersion": 1,
            "currentSceneId": "start", "terminal": False}


def projection():
    return {"coins": {"confirmed": 10}, "achievements": {}, "derived": {},
            "checkpoint": {**checkpoint(), "currentSceneId": "next"}}


@pytest_asyncio.fixture
async def store():
    uri = os.environ.get("TEST_MONGO_URI")
    if not uri:
        pytest.skip("TEST_MONGO_URI required: never use production MongoDB")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    db = client[f"phase6b_attributed_adapter_{uuid4().hex}"]
    try:
        await client.admin.command("ping")
        adapter = AttributedMongoReservationStore(db.ledgers, db.events)
        await adapter.ensure_indexes()
        yield adapter
    finally:
        await client.drop_database(db.name)
        client.close()


async def reserved(store, *, history=None):
    ledger_id = uuid4().hex
    owner_id = uuid4().hex
    await store.ledgers.insert_one({
        "_id": ledger_id, "ownerType": "account", "ownerId": owner_id,
        "progressionRevision": 0, "checkpoint": checkpoint(),
        "appliedEventIds": {} if history is None else history,
        "coins": {"confirmed": 0}, "achievements": {}, "derived": {},
    })
    event = await store.reserve(
        ledger_id=ledger_id, event_id=str(uuid4()), payload_hash="digest",
        base_revision=0, awards={"coins": 10}, next_projection=projection(),
        expected_checkpoint=checkpoint(), expected_owner_type="account",
        expected_owner_id=owner_id,
    )
    return event


@pytest.mark.asyncio
async def test_commit_and_finalise_are_attributed_and_idempotent(store):
    event = await reserved(store)
    committed = await store.commit(event=event, lease_owner=event["leaseOwner"])
    assert committed["appliedEventIds"] == {"1": event["eventId"]}
    assert committed["coins"]["confirmed"] == 10
    first = await store.finalise(event=event, payload_hash="digest")
    second = await store.finalise(event=event, payload_hash="digest")
    assert first["status"] == second["status"] == "applied"
    assert first["appliedAt"] == second["appliedAt"]
    assert (await store.ledgers.find_one({"_id": event["ledgerId"]}))["coins"]["confirmed"] == 10


@pytest.mark.asyncio
@pytest.mark.parametrize("revision", [1, 4])
async def test_foreign_revision_fails_closed_in_finalise_and_recover(store, revision):
    event = await reserved(store)
    await store.ledgers.update_one({"_id": event["ledgerId"]},
                                   {"$set": {"progressionRevision": revision}})
    with pytest.raises(AttributionUnproven):
        await store.finalise(event=event, payload_hash="digest")
    with pytest.raises(AttributionUnproven):
        await store.recover(event)
    assert (await store.events.find_one({"_id": event["_id"]}))["status"] == "committing"


@pytest.mark.asyncio
async def test_commit_cannot_claim_foreign_revision(store):
    event = await reserved(store)
    await store.ledgers.update_one({"_id": event["ledgerId"]},
                                   {"$set": {"progressionRevision": 1,
                                             "appliedEventIds.1": "foreign"}})
    with pytest.raises(AttributionUnproven):
        await store.commit(event=event, lease_owner=event["leaseOwner"])
    ledger = await store.ledgers.find_one({"_id": event["ledgerId"]})
    assert ledger["coins"]["confirmed"] == 0
    assert ledger["appliedEventIds"] == {"1": "foreign"}


@pytest.mark.asyncio
async def test_recovery_after_commit_does_not_grant_twice(store):
    event = await reserved(store)
    await store.commit(event=event, lease_owner=event["leaseOwner"])
    recovered = await store.recover(event)
    assert recovered["status"] == "applied"
    assert (await store.ledgers.find_one({"_id": event["ledgerId"]}))["coins"]["confirmed"] == 10
    assert (await store.recover(recovered))["status"] == "applied"


@pytest.mark.asyncio
async def test_expired_uncommitted_reservation_recovers_once(store):
    event = await reserved(store)
    await store.events.update_one({"_id": event["_id"]},
                                  {"$set": {"leaseUntil": datetime.now(timezone.utc) - timedelta(seconds=5)}})
    recovered = await store.recover(event)
    assert recovered["status"] == "applied"
    ledger = await store.ledgers.find_one({"_id": event["ledgerId"]})
    assert ledger["progressionRevision"] == 1
    assert ledger["appliedEventIds"] == {"1": event["eventId"]}
    assert ledger["coins"]["confirmed"] == 10


@pytest.mark.asyncio
async def test_missing_history_cannot_commit_or_finalise(store):
    event = await reserved(store)
    await store.ledgers.update_one({"_id": event["ledgerId"]}, {"$unset": {"appliedEventIds": ""}})
    with pytest.raises(AttributionUnproven):
        await store.commit(event=event, lease_owner=event["leaseOwner"])
    with pytest.raises(AttributionUnproven):
        await store.finalise(event=event, payload_hash="digest")
    assert (await store.ledgers.find_one({"_id": event["ledgerId"]}))["progressionRevision"] == 0


@pytest.mark.asyncio
async def test_owner_change_after_reservation_cannot_commit_award(store):
    event = await reserved(store)
    await store.ledgers.update_one(
        {"_id": event["ledgerId"]},
        {"$set": {"ownerId": "different-account"}},
    )
    with pytest.raises(AttributionUnproven, match="CAS did not match"):
        await store.commit(event=event, lease_owner=event["leaseOwner"])
    ledger = await store.ledgers.find_one({"_id": event["ledgerId"]})
    assert ledger["progressionRevision"] == 0
    assert ledger["coins"]["confirmed"] == 0
    assert ledger["appliedEventIds"] == {}
    persisted = await store.events.find_one({"_id": event["_id"]})
    assert persisted["status"] == "committing"
    assert persisted["expectedOwnerId"] == event["expectedOwnerId"]
