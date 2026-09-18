"""Inert opening grant integration tests; TEST_MONGO_URI must be disposable."""
import asyncio
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from progression.clean_ledger import InvalidCleanLedger
from progression.opening_grant import OPENING_BLOOD_COINS, initialize_granted_account_ledger


def registry():
    return {"characters": {"friend": 0}, "books": {"book1": {"version": 1,
            "scenes": {"start": {"choices": {}}}}}}


def args(owner_id="account-one"):
    return {"owner_id": owner_id, "book_id": "book1", "content_version": 1,
            "scene_id": "start"}


@pytest_asyncio.fixture
async def ledgers():
    uri = os.environ.get("TEST_MONGO_URI")
    if not uri:
        pytest.skip("TEST_MONGO_URI required: never use production MongoDB")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    db = client[f"phase6b_opening_grant_{uuid4().hex}"]
    try:
        await client.admin.command("ping")
        await db.ledgers.create_index([("ownerType", 1), ("ownerId", 1)], unique=True)
        yield db.ledgers
    finally:
        await client.drop_database(db.name)
        client.close()


@pytest.mark.asyncio
async def test_concurrent_first_signins_create_one_grant(ledgers):
    results = await asyncio.gather(*(initialize_granted_account_ledger(
        ledgers, registry(), **args()) for _ in range(24)))
    assert OPENING_BLOOD_COINS == 50
    assert len({doc["_id"] for doc in results}) == 1
    assert await ledgers.count_documents({"ownerType": "account", "ownerId": "account-one"}) == 1
    stored = await ledgers.find_one({"_id": results[0]["_id"]})
    assert stored["coins"] == {"confirmed": 50}
    assert stored["openingGranted"] is True
    assert stored["progressionRevision"] == 0 and stored["appliedEventIds"] == {}
    assert stored["achievements"] == {}
    results[0]["coins"]["confirmed"] = 900
    assert (await ledgers.find_one({"_id": stored["_id"]}))["coins"]["confirmed"] == 50


@pytest.mark.asyncio
async def test_repeat_signin_never_regrants_or_overwrites_progress(ledgers):
    first = await initialize_granted_account_ledger(ledgers, registry(), **args())
    await ledgers.update_one({"_id": first["_id"]}, {"$set": {
        "coins.confirmed": 17, "progressionRevision": 3,
        "checkpoint.currentSceneId": "later", "achievements.first": True}})
    again = await initialize_granted_account_ledger(ledgers, registry(), **args())
    assert again["_id"] == first["_id"]
    assert again["coins"]["confirmed"] == 17
    assert again["progressionRevision"] == 3
    assert again["checkpoint"]["currentSceneId"] == "later"
    assert again["achievements"] == {"first": True}
    assert again["openingGranted"] is True


@pytest.mark.asyncio
async def test_existing_unawarded_ledger_is_not_silently_granted_or_migrated(ledgers):
    await ledgers.insert_one({"_id": "legacy", "ownerType": "account", "ownerId": "account-one",
                              "coins": {"confirmed": 0}, "openingGranted": False})
    existing = await initialize_granted_account_ledger(ledgers, registry(), **args())
    assert existing["_id"] == "legacy"
    assert existing["coins"] == {"confirmed": 0}
    assert existing["openingGranted"] is False
    assert await ledgers.count_documents({}) == 1


@pytest.mark.asyncio
async def test_anonymous_or_missing_account_identity_cannot_receive_grant(ledgers):
    for owner in ("", "   ", None):
        with pytest.raises(InvalidCleanLedger):
            await initialize_granted_account_ledger(ledgers, registry(), **args(owner))
    assert await ledgers.count_documents({}) == 0


@pytest.mark.asyncio
async def test_invalid_trusted_content_cannot_create_grant(ledgers):
    with pytest.raises(InvalidCleanLedger):
        await initialize_granted_account_ledger(ledgers, registry(), **{
            **args(), "content_version": 999})
    assert await ledgers.count_documents({}) == 0
