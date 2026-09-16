"""Inert story claim tests; TEST_MONGO_URI must point to disposable MongoDB."""
import asyncio
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from progression.story_claim import StoryClaimConflict, StoryClaimDenied, claim_story_only


@pytest_asyncio.fixture
async def collections():
    uri = os.environ.get("TEST_MONGO_URI")
    if not uri:
        pytest.skip("TEST_MONGO_URI required; never use production MongoDB")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    db = client["phase6b_story_claim_" + uuid4().hex]
    try:
        await client.admin.command("ping")
        await db.account_saves.create_index("userId", unique=True)
        await db.anonymous_saves.create_index("playerId", unique=True)
        yield db.anonymous_saves, db.account_saves
    finally:
        await client.drop_database(db.name)
        client.close()


def anonymous_doc(player_id="vc_abcdefgh", revision=2):
    return {"playerId": player_id, "revision": revision, "saveSchemaVersion": 3,
            "contentVersions": {"book1": 1}, "playerState": {
                "player": {"name": "Mara"}, "relationships": {"friend": 4},
                "flags": {"saved_friend": True},
                "progress": {"currentBookId": "book1", "currentChapter": 2,
                             "currentSceneId": "forest", "completedChapters": [1],
                             "completedBooks": [], "sceneHistory": ["start", "forest"]},
                "settings": {}, "version": 3, "bloodCoins": 99999,
                "achievements": {"FIRST_CHOICE": True}, "dailyStreak": 300,
                "lastLoginDate": "2026-09-16", "premiumEntitlements": True}}


def claim(anon, account, **changes):
    kwargs = {"authenticated_user_id": "user-one", "player_id": "vc_abcdefgh",
              "expected_anonymous_revision": 2, "now": "2026-09-16T18:00:00Z"}
    kwargs.update(changes)
    return claim_story_only(anon, account, **kwargs)


@pytest.mark.asyncio
async def test_claim_preserves_story_but_not_rewards_and_retry_is_idempotent(collections):
    anon, account = collections
    await anon.insert_one(anonymous_doc())
    first = await claim(anon, account)
    assert first["playerState"]["progress"]["currentSceneId"] == "forest"
    assert first["playerState"]["relationships"] == {"friend": 4}
    assert first["playerState"]["bloodCoins"] == 0
    assert first["playerState"]["achievements"] == {}
    assert "premiumEntitlements" not in first["playerState"]
    assert (await anon.find_one({"playerId": "vc_abcdefgh"}))["claimedBy"] == "user-one"
    second = await claim(anon, account)
    assert second["_id"] == first["_id"]
    assert await account.count_documents({}) == 1


@pytest.mark.asyncio
async def test_stale_revision_does_not_fence_or_create(collections):
    anon, account = collections
    await anon.insert_one(anonymous_doc())
    with pytest.raises(StoryClaimConflict):
        await claim(anon, account, expected_anonymous_revision=1)
    assert "claimedBy" not in await anon.find_one({"playerId": "vc_abcdefgh"})
    assert await account.count_documents({}) == 0


@pytest.mark.asyncio
async def test_existing_account_requires_explicit_resolution(collections):
    anon, account = collections
    await anon.insert_one(anonymous_doc())
    await account.insert_one({"userId": "user-one", "revision": 5, "playerState": {"bloodCoins": 1}})
    with pytest.raises(StoryClaimConflict):
        await claim(anon, account)
    assert "claimedBy" not in await anon.find_one({"playerId": "vc_abcdefgh"})
    assert (await account.find_one({"userId": "user-one"}))["revision"] == 5


@pytest.mark.asyncio
async def test_other_account_cannot_claim_fenced_save(collections):
    anon, account = collections
    doc = anonymous_doc()
    doc["claimedBy"] = "user-two"
    await anon.insert_one(doc)
    with pytest.raises(StoryClaimDenied):
        await claim(anon, account)
    assert await account.count_documents({}) == 0


@pytest.mark.asyncio
async def test_concurrent_identical_claims_create_one_account_save(collections):
    anon, account = collections
    await anon.insert_one(anonymous_doc())
    outcomes = await asyncio.gather(*(claim(anon, account) for _ in range(12)))
    assert len({item["_id"] for item in outcomes}) == 1
    assert await account.count_documents({}) == 1


@pytest.mark.asyncio
async def test_missing_authenticated_identity_cannot_claim(collections):
    anon, account = collections
    await anon.insert_one(anonymous_doc())
    with pytest.raises(StoryClaimDenied):
        await claim(anon, account, authenticated_user_id="")
    assert "claimedBy" not in await anon.find_one({"playerId": "vc_abcdefgh"})
