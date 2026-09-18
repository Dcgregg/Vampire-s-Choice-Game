"""Transaction rollback regression; requires disposable TEST_MONGO_URI replica set."""
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from progression.story_claim import StoryClaimConflict, claim_story_only
from test_story_claim_mongo_integration import anonymous_doc


@pytest_asyncio.fixture
async def collections():
    uri = os.environ.get("TEST_MONGO_URI")
    if not uri:
        pytest.skip("TEST_MONGO_URI required; never use production MongoDB")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    db = client["phase6b_claim_txn_" + uuid4().hex]
    try:
        await client.admin.command("ping")
        await db.account_saves.create_index("userId", unique=True)
        await db.anonymous_saves.create_index("playerId", unique=True)
        yield db.anonymous_saves, db.account_saves
    finally:
        await client.drop_database(db.name)
        client.close()


class FailingInsert:
    """Fail only after the transaction has written its anonymous-save fence."""
    def __init__(self, collection):
        self.collection = collection
        self.database = collection.database

    async def find_one(self, *args, **kwargs):
        return await self.collection.find_one(*args, **kwargs)

    async def insert_one(self, *args, **kwargs):
        raise RuntimeError("injected account insert failure")


@pytest.mark.asyncio
async def test_account_insert_failure_rolls_back_anonymous_fence(collections):
    anon, account = collections
    await anon.insert_one(anonymous_doc())
    args = dict(authenticated_user_id="user-one", player_id="vc_abcdefgh",
                expected_anonymous_revision=2, now="2026-09-16T18:00:00Z")
    with pytest.raises(RuntimeError, match="injected account insert failure"):
        await claim_story_only(anon, FailingInsert(account), **args)
    saved = await anon.find_one({"playerId": "vc_abcdefgh"})
    assert "claimedBy" not in saved
    assert await account.count_documents({}) == 0
    first = await claim_story_only(anon, account, **args)
    second = await claim_story_only(anon, account, **args)
    assert first["_id"] == second["_id"]
    assert await account.count_documents({}) == 1


@pytest.mark.asyncio
async def test_existing_account_conflict_never_fences_anonymous_save(collections):
    anon, account = collections
    await anon.insert_one(anonymous_doc())
    await account.insert_one({"userId": "user-one", "revision": 7})
    with pytest.raises(StoryClaimConflict):
        await claim_story_only(anon, account, authenticated_user_id="user-one",
                               player_id="vc_abcdefgh", expected_anonymous_revision=2,
                               now="2026-09-16T18:00:00Z")
    assert "claimedBy" not in await anon.find_one({"playerId": "vc_abcdefgh"})
    assert (await account.find_one({"userId": "user-one"}))["revision"] == 7
