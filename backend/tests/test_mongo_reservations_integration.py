"""Real MongoDB tests; TEST_MONGO_URI must point to a disposable database."""
import asyncio
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from progression.mongo_reservations import (
    MongoReservationStore, ProgressionConflict, ReservationInvariantError,
)


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


async def seeded(store):
    ledger_id = uuid4().hex
    checkpoint = {"bookId": "book1", "currentSceneId": "start", "terminal": False}
    await store.ledgers.insert_one({"_id": ledger_id, "ownerType": "anon", "ownerId": uuid4().hex,
                                    "progressionRevision": 0, "checkpoint": checkpoint,
                                    "coins": {"confirmed": 250}, "achievements": {}, "derived": {}})
    return ledger_id, checkpoint


def projection(coins=260):
    return {"coins": {"confirmed": coins}, "achievements": {}, "derived": {},
            "checkpoint": {"bookId": "book1", "currentSceneId": "next", "terminal": False}}


@pytest.mark.asyncio
async def test_one_target_revision_has_one_winner(mongo_store):
    store = mongo_store
    ledger_id, checkpoint = await seeded(store)

    async def attempt(event_id):
        try:
            return await store.reserve(ledger_id=ledger_id, event_id=event_id,
                                       payload_hash=event_id, base_revision=0, awards={},
                                       next_projection=projection(), expected_checkpoint=checkpoint)
        except ProgressionConflict:
            return None

    results = await asyncio.gather(attempt("one"), attempt("two"))
    assert sum(event is not None and event.get("status") == "committing" for event in results) == 1
    assert await store.events.count_documents({"ledgerId": ledger_id, "targetRevision": 1}) == 1


@pytest.mark.asyncio
async def test_commit_and_finalise_are_idempotent(mongo_store):
    store = mongo_store
    ledger_id, checkpoint = await seeded(store)
    event = await store.reserve(ledger_id=ledger_id, event_id="once", payload_hash="digest",
                                base_revision=0, awards={"coins": 10},
                                next_projection=projection(), expected_checkpoint=checkpoint)
    first = await store.commit(event=event, lease_owner=event["leaseOwner"])
    assert first["progressionRevision"] == 1
    applied = await store.finalise(event=event, payload_hash="digest")
    assert applied["status"] == "applied"
    assert (await store.ledgers.find_one({"_id": ledger_id}))["coins"]["confirmed"] == 260
    assert (await store.events.count_documents({"ledgerId": ledger_id, "eventId": "once"})) == 1
    repeated = await store.reserve(ledger_id=ledger_id, event_id="once", payload_hash="digest",
                                   base_revision=0, awards={"coins": 10})
    assert repeated["status"] == "applied"


@pytest.mark.asyncio
async def test_stale_reservation_cannot_claim_already_committed_revision(mongo_store):
    store = mongo_store
    ledger_id, checkpoint = await seeded(store)
    await store.ledgers.update_one({"_id": ledger_id}, {"$set": {"progressionRevision": 1}})
    with pytest.raises(ProgressionConflict, match="revision changed"):
        await store.reserve(ledger_id=ledger_id, event_id="late", payload_hash="late",
                            base_revision=0, awards={}, next_projection=projection(),
                            expected_checkpoint=checkpoint)
    assert await store.events.count_documents({"ledgerId": ledger_id, "targetRevision": 1}) == 0


@pytest.mark.asyncio
async def test_recovery_completes_expired_reservation_without_recomputing(mongo_store):
    store = mongo_store
    ledger_id, checkpoint = await seeded(store)
    event = await store.reserve(ledger_id=ledger_id, event_id="recover", payload_hash="hash",
                                base_revision=0, awards={"coins": 10},
                                next_projection=projection(), expected_checkpoint=checkpoint)
    await store.events.update_one({"_id": event["_id"]}, {"$set": {"leaseUntil": event["createdAt"]}})
    result = await store.recover(event)
    assert result["status"] == "applied"
    ledger = await store.ledgers.find_one({"_id": ledger_id})
    assert ledger["progressionRevision"] == 1
    assert ledger["coins"]["confirmed"] == 260
    assert (await store.recover(result))["status"] == "applied"


@pytest.mark.asyncio
async def test_recovery_after_commit_before_finalise_does_not_award_twice(mongo_store):
    store = mongo_store
    ledger_id, checkpoint = await seeded(store)
    event = await store.reserve(ledger_id=ledger_id, event_id="crash", payload_hash="hash",
                                base_revision=0, awards={"coins": 10},
                                next_projection=projection(), expected_checkpoint=checkpoint)
    await store.commit(event=event, lease_owner=event["leaseOwner"])
    result = await store.recover(event)
    assert result["status"] == "applied"
    assert (await store.ledgers.find_one({"_id": ledger_id}))["coins"]["confirmed"] == 260


@pytest.mark.asyncio
async def test_caller_cannot_substitute_a_different_reward_projection(mongo_store):
    store = mongo_store
    ledger_id, checkpoint = await seeded(store)
    event = await store.reserve(ledger_id=ledger_id, event_id="immutable", payload_hash="hash",
                                base_revision=0, awards={}, next_projection=projection(),
                                expected_checkpoint=checkpoint)
    with pytest.raises(ReservationInvariantError, match="differs"):
        await store.commit(event=event, lease_owner=event["leaseOwner"],
                           next_projection=projection(9999))
    assert (await store.ledgers.find_one({"_id": ledger_id}))["progressionRevision"] == 0
