"""Index precondition regressions; TEST_MONGO_URI must point to disposable MongoDB."""
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from progression.clean_ledger import InvalidCleanLedger
from progression.opening_grant import initialize_granted_account_ledger


@pytest_asyncio.fixture
async def ledgers():
    uri = os.environ.get("TEST_MONGO_URI")
    if not uri:
        pytest.skip("TEST_MONGO_URI required: never use production MongoDB")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    db = client[f"phase6b_grant_index_{uuid4().hex}"]
    try:
        await client.admin.command("ping")
        yield db.ledgers
    finally:
        await client.drop_database(db.name)
        client.close()


async def attempt(ledgers):
    return await initialize_granted_account_ledger(
        ledgers,
        {"characters": {"friend": 0}, "books": {"book1": {"version": 1,
            "scenes": {"start": {"choices": {}}}}}},
        owner_id="account-one", book_id="book1", content_version=1, scene_id="start",
    )


@pytest.mark.asyncio
async def test_missing_owner_index_refuses_grant(ledgers):
    with pytest.raises(InvalidCleanLedger, match="unique account owner index required"):
        await attempt(ledgers)
    assert await ledgers.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("index_options", [{}, {"unique": True, "sparse": True},
                                         {"unique": True, "partialFilterExpression": {"ownerType": "account"}}])
async def test_nonunique_or_incomplete_owner_index_refuses_grant(ledgers, index_options):
    await ledgers.create_index([("ownerType", 1), ("ownerId", 1)], **index_options)
    with pytest.raises(InvalidCleanLedger, match="unique account owner index required"):
        await attempt(ledgers)
    assert await ledgers.count_documents({}) == 0


@pytest.mark.asyncio
async def test_full_unique_owner_index_allows_one_grant(ledgers):
    await ledgers.create_index([("ownerType", 1), ("ownerId", 1)], unique=True)
    first = await attempt(ledgers)
    second = await attempt(ledgers)
    assert first["_id"] == second["_id"]
    assert first["coins"] == second["coins"] == {"confirmed": 50}
    assert await ledgers.count_documents({}) == 1
