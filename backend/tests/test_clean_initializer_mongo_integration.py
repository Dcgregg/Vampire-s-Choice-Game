"""Real MongoDB initializer tests. TEST_MONGO_URI must be disposable, never production."""
import asyncio
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from progression.clean_initializer import initialize_clean_account_ledger
from progression.clean_ledger import InvalidCleanLedger


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
        pytest.skip("TEST_MONGO_URI not set: no disposable MongoDB")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    database = client[f"phase6b_clean_init_{uuid4().hex}"]
    try:
        await client.admin.command("ping")
        await database.ledgers.create_index([("ownerType", 1), ("ownerId", 1)], unique=True)
        yield database.ledgers
    finally:
        await client.drop_database(database.name)
        client.close()


@pytest.mark.asyncio
async def test_real_unique_index_concurrent_initializers_return_one_seed(ledgers):
    results = await asyncio.gather(*(initialize_clean_account_ledger(
        ledgers, registry(), **args()) for _ in range(24)))
    assert len({result["_id"] for result in results}) == 1
    assert await ledgers.count_documents({"ownerType": "account", "ownerId": "account-one"}) == 1
    stored = await ledgers.find_one({"ownerType": "account", "ownerId": "account-one"})
    assert stored["_id"] == results[0]["_id"]
    assert stored["progressionRevision"] == 0
    assert stored["coins"] == {"confirmed": 0}
    assert stored["achievements"] == {} and stored["openingGranted"] is False
    assert stored["lifecycleApplied"] == []
    assert stored["checkpoint"] == {"bookId": "book1", "contentVersion": 1,
                                    "currentSceneId": "start", "terminal": False}
    results[0]["coins"]["confirmed"] = 999
    assert (await ledgers.find_one({"_id": stored["_id"]}))["coins"]["confirmed"] == 0


@pytest.mark.asyncio
async def test_real_mongo_existing_progress_is_unchanged(ledgers):
    first = await initialize_clean_account_ledger(ledgers, registry(), **args())
    await ledgers.update_one({"_id": first["_id"]}, {"$set": {
        "progressionRevision": 4, "coins.confirmed": 19}})
    again = await initialize_clean_account_ledger(ledgers, registry(), **args())
    assert again["_id"] == first["_id"]
    assert again["progressionRevision"] == 4 and again["coins"]["confirmed"] == 19
    assert await ledgers.count_documents({"ownerType": "account", "ownerId": "account-one"}) == 1


@pytest.mark.asyncio
async def test_real_mongo_retired_opening_content_does_not_hide_existing_ledger(ledgers):
    first = await initialize_clean_account_ledger(ledgers, registry(), **args())
    await ledgers.update_one({"_id": first["_id"]}, {"$set": {
        "progressionRevision": 4, "coins.confirmed": 19}})
    # This registry no longer contains the opening book. Existing account
    # discovery must not depend on the current new-account opening configuration.
    retired_registry = {"characters": {"friend": 0}, "books": {}}
    again = await initialize_clean_account_ledger(ledgers, retired_registry, **args())
    assert again["_id"] == first["_id"]
    assert again["progressionRevision"] == 4
    assert again["coins"]["confirmed"] == 19
    assert again["checkpoint"]["contentVersion"] == 1
    assert await ledgers.count_documents({"ownerType": "account", "ownerId": "account-one"}) == 1
    # Retired opening content must still prevent creation of a *new* account.
    with pytest.raises(InvalidCleanLedger):
        await initialize_clean_account_ledger(ledgers, retired_registry, **args("account-two"))
    assert await ledgers.count_documents({}) == 1


@pytest.mark.asyncio
async def test_real_mongo_invalid_content_does_not_create_ledger(ledgers):
    with pytest.raises(InvalidCleanLedger):
        await initialize_clean_account_ledger(ledgers, registry(), **{
            **args(), "content_version": 2})
    assert await ledgers.count_documents({}) == 0


@pytest.mark.asyncio
async def test_real_mongo_distinct_accounts_get_distinct_ledgers(ledgers):
    first, second = await asyncio.gather(
        initialize_clean_account_ledger(ledgers, registry(), **args("account-one")),
        initialize_clean_account_ledger(ledgers, registry(), **args("account-two")),
    )
    assert first["_id"] != second["_id"]
    assert await ledgers.count_documents({}) == 2
