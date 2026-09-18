"""Disposable MongoDB only; exercises an inert attributed write candidate."""
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from progression.attributed_ledger_write import write_attributed_revision
from progression.attribution import AttributionUnproven, require_event_attribution


@pytest_asyncio.fixture
async def ledger_collection():
    uri = os.environ.get("TEST_MONGO_URI")
    if not uri:
        pytest.skip("TEST_MONGO_URI required for disposable MongoDB tests")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    db = client[f"phase6b_attribution_{uuid4().hex}"]
    try:
        await client.admin.command("ping")
        yield db.ledgers
    finally:
        await client.drop_database(db.name)
        client.close()


def checkpoint():
    return {"bookId": "book1", "contentVersion": 1,
            "currentSceneId": "start", "terminal": False}


def projection():
    return {"coins": {"confirmed": 10}, "achievements": {}, "derived": {},
            "checkpoint": {**checkpoint(), "currentSceneId": "next"}}


async def seed(ledgers):
    ledger_id = uuid4().hex
    await ledgers.insert_one({"_id": ledger_id, "progressionRevision": 0,
                              "checkpoint": checkpoint(), "appliedEventIds": {},
                              "coins": {"confirmed": 0}})
    return ledger_id


async def write(ledgers, event):
    async with await ledgers.database.client.start_session() as session:
        async with session.start_transaction():
            return await write_attributed_revision(
                ledgers, event=event, projection=projection(),
                expected_checkpoint=checkpoint(), session=session)


@pytest.mark.asyncio
async def test_attribution_is_atomic_with_projection_and_survives_later_revision(ledger_collection):
    ledgers = ledger_collection
    ledger_id = await seed(ledgers)
    event = {"ledgerId": ledger_id, "eventId": "first", "baseRevision": 0, "targetRevision": 1}
    result = await write(ledgers, event)
    assert result["coins"]["confirmed"] == 10
    assert result["appliedEventIds"] == {"1": "first"}
    await ledgers.update_one({"_id": ledger_id}, {"$set": {"progressionRevision": 2,
        "appliedEventIds.2": "later"}})
    require_event_attribution(await ledgers.find_one({"_id": ledger_id}), event)


@pytest.mark.asyncio
async def test_foreign_revision_cannot_be_claimed_by_event(ledger_collection):
    ledgers = ledger_collection
    ledger_id = await seed(ledgers)
    event = {"ledgerId": ledger_id, "eventId": "first", "baseRevision": 0, "targetRevision": 1}
    await ledgers.update_one({"_id": ledger_id}, {"$set": {"progressionRevision": 1,
        "appliedEventIds.1": "foreign"}})
    with pytest.raises(AttributionUnproven, match="CAS did not match"):
        await write(ledgers, event)
    current = await ledgers.find_one({"_id": ledger_id})
    assert current["coins"]["confirmed"] == 0
    assert current["appliedEventIds"] == {"1": "foreign"}


@pytest.mark.asyncio
async def test_missing_attribution_schema_fails_closed(ledger_collection):
    ledgers = ledger_collection
    ledger_id = await seed(ledgers)
    await ledgers.update_one({"_id": ledger_id}, {"$unset": {"appliedEventIds": ""}})
    event = {"ledgerId": ledger_id, "eventId": "first", "baseRevision": 0, "targetRevision": 1}
    with pytest.raises(AttributionUnproven, match="CAS did not match"):
        await write(ledgers, event)
    assert (await ledgers.find_one({"_id": ledger_id}))["progressionRevision"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("history", [{}, {"1": ""}, {"1": None}, {"1": 7}])
async def test_nonopening_write_rejects_missing_or_invalid_predecessor(ledger_collection, history):
    ledgers = ledger_collection
    ledger_id = await seed(ledgers)
    await ledgers.update_one({"_id": ledger_id}, {"$set": {
        "progressionRevision": 1, "appliedEventIds": history}})
    event = {"ledgerId": ledger_id, "eventId": "second", "baseRevision": 1, "targetRevision": 2}
    with pytest.raises(AttributionUnproven, match="CAS did not match"):
        await write(ledgers, event)
    current = await ledgers.find_one({"_id": ledger_id})
    assert current["progressionRevision"] == 1
    assert current["coins"]["confirmed"] == 0
    assert current["appliedEventIds"] == history


@pytest.mark.asyncio
async def test_nonopening_write_retains_predecessor_marker(ledger_collection):
    ledgers = ledger_collection
    ledger_id = await seed(ledgers)
    await ledgers.update_one({"_id": ledger_id}, {"$set": {
        "progressionRevision": 1, "appliedEventIds.1": "first"}})
    event = {"ledgerId": ledger_id, "eventId": "second", "baseRevision": 1, "targetRevision": 2}
    result = await write(ledgers, event)
    assert result["appliedEventIds"] == {"1": "first", "2": "second"}
    assert result["progressionRevision"] == 2
