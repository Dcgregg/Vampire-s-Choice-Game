"""Disposable-Mongo proof that legacy story and trusted rewards stay separate."""
import pytest

from progression.account_progression_bootstrap import bootstrap_account_progression
from progression.anonymous_claim_proof import issue_claim_credential
from progression.credentialed_story_claim import claim_story_with_credential
from test_story_claim_mongo_integration import anonymous_doc
from test_story_claim_transaction_integration import collections  # noqa: F401


def registry():
    return {"characters": {"friend": 0}, "books": {"book1": {"version": 1,
            "scenes": {"start": {"choices": {}}}}}}


@pytest.mark.asyncio
async def test_story_claim_and_account_grant_are_idempotent_and_separate(collections):
    anonymous_saves, account_saves = collections
    ledgers = anonymous_saves.database.progression_ledgers
    await ledgers.create_index([("ownerType", 1), ("ownerId", 1)], unique=True)
    secret, digest = issue_claim_credential()
    source = anonymous_doc()
    source["claimCredentialDigest"] = digest
    await anonymous_saves.insert_one(source)

    claim_args = dict(
        authenticated_user_id="user-one", player_id="vc_abcdefgh",
        expected_anonymous_revision=2, claim_credential=secret, now="now",
    )
    story = await claim_story_with_credential(
        anonymous_saves, account_saves, **claim_args,
    )
    ledger = await bootstrap_account_progression(
        ledgers, registry(), authenticated_user_id="user-one",
        book_id="book1", content_version=1, scene_id="start",
    )

    assert story["playerState"]["progress"]["currentSceneId"] == "forest"
    assert story["playerState"]["relationships"] == {"friend": 4}
    assert story["playerState"]["bloodCoins"] == 0
    assert story["playerState"]["achievements"] == {}
    assert "premiumEntitlements" not in story["playerState"]
    assert ledger["coins"] == {"confirmed": 50}
    assert ledger["achievements"] == {}
    assert ledger["progressionRevision"] == 0

    await account_saves.update_one(
        {"userId": "user-one"},
        {"$set": {"playerState.bloodCoins": 999999,
                  "playerState.achievements": {"FORGED": True}}},
    )
    unchanged = await ledgers.find_one({"ownerType": "account", "ownerId": "user-one"})
    assert unchanged["coins"] == {"confirmed": 50}
    assert unchanged["derived"]["coins"] == 50
    assert unchanged["achievements"] == {}

    repeated_story = await claim_story_with_credential(
        anonymous_saves, account_saves, **claim_args,
    )
    repeated_ledger = await bootstrap_account_progression(
        ledgers, registry(), authenticated_user_id="user-one",
        book_id="book1", content_version=1, scene_id="start",
    )
    assert repeated_story["_id"] == story["_id"]
    assert repeated_ledger == ledger
    assert await account_saves.count_documents({"userId": "user-one"}) == 1
    assert await ledgers.count_documents({"ownerType": "account", "ownerId": "user-one"}) == 1
