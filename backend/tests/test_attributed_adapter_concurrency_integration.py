"""Concurrency regressions for the inert attributed adapter; disposable MongoDB only."""
import asyncio
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from progression.attribution import AttributionUnproven
from progression.attributed_mongo_reservations import AttributedMongoReservationStore
from progression.mongo_reservations import ProgressionConflict, ReservationBusy


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


@pytest.mark.asyncio
async def test_recovery_after_commit_before_finalisation_is_idempotent(case):
    store, event = case
    await store.commit(event=event, lease_owner=event["leaseOwner"])
    pending = await store.events.find_one({"_id": event["_id"]})
    assert pending["status"] == "committing"
    recovered = await store.recover(pending)
    retried = await store.recover(recovered)
    ledger = await store.ledgers.find_one({"_id": event["ledgerId"]})
    assert recovered["status"] == retried["status"] == "applied"
    assert recovered["resultRevision"] == retried["resultRevision"] == 1
    assert ledger["progressionRevision"] == 1
    assert ledger["coins"]["confirmed"] == 10
    assert ledger["appliedEventIds"] == {"1": event["eventId"]}


@pytest.mark.asyncio
async def test_recovery_rejects_applied_status_if_attribution_disappears(case):
    store, event = case
    await store.commit(event=event, lease_owner=event["leaseOwner"])
    applied = await store.finalise(event=event, payload_hash="digest")
    await store.ledgers.update_one(
        {"_id": event["ledgerId"]}, {"$unset": {"appliedEventIds.1": ""}},
    )
    with pytest.raises(AttributionUnproven):
        await store.recover(applied)
    persisted = await store.events.find_one({"_id": event["_id"]})
    assert persisted["status"] == "applied"
    assert persisted["resultRevision"] == 1


@pytest.mark.asyncio
async def test_distinct_event_ids_cannot_reserve_or_award_same_revision(case):
    store, first = case
    checkpoint = first["expectedCheckpoint"]
    second_id = str(uuid4())
    second_projection = {
        "coins": {"confirmed": 99}, "achievements": {}, "derived": {},
        "checkpoint": {**checkpoint, "currentSceneId": "other"},
    }
    # A competing event must not be able to claim revision 1 while the first
    # event has a durable reservation, even though the ledger is still at 0.
    with pytest.raises(ProgressionConflict, match="target revision already reserved"):
        await store.reserve(
            ledger_id=first["ledgerId"], event_id=second_id,
            payload_hash="other-digest", base_revision=0,
            awards={"coins": 99}, next_projection=second_projection,
            expected_checkpoint=checkpoint,
        )
    await store.commit(event=first, lease_owner=first["leaseOwner"])
    applied = await store.finalise(event=first, payload_hash="digest")
    assert applied["status"] == "applied"
    with pytest.raises(ProgressionConflict, match="ledger revision changed"):
        await store.reserve(
            ledger_id=first["ledgerId"], event_id=second_id,
            payload_hash="other-digest", base_revision=0,
            awards={"coins": 99}, next_projection=second_projection,
            expected_checkpoint=checkpoint,
        )
    ledger = await store.ledgers.find_one({"_id": first["ledgerId"]})
    loser = await store.events.find_one({"ledgerId": first["ledgerId"], "eventId": second_id})
    assert ledger["progressionRevision"] == 1
    assert ledger["coins"]["confirmed"] == 10
    assert ledger["appliedEventIds"] == {"1": first["eventId"]}
    assert loser["status"] == "received"
    assert "targetRevision" not in loser
