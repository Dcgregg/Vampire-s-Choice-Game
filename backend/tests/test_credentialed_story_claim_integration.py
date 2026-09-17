"""Disposable MongoDB replica set only; never point TEST_MONGO_URI at production."""
import pytest

from progression.anonymous_claim_proof import issue_claim_credential
from progression.credentialed_story_claim import claim_story_with_credential
from progression.story_claim import StoryClaimConflict, StoryClaimDenied
from test_story_claim_transaction_integration import collections  # noqa: F401
from test_story_claim_mongo_integration import anonymous_doc


@pytest.mark.asyncio
async def test_credentialed_claim_preserves_story_and_strips_rewards(collections):
    anon, account = collections
    secret, digest = issue_claim_credential()
    doc = anonymous_doc()
    doc['claimCredentialDigest'] = digest
    await anon.insert_one(doc)
    args = dict(authenticated_user_id='user-one', player_id='vc_abcdefgh',
                expected_anonymous_revision=2, claim_credential=secret, now='now')
    with pytest.raises(StoryClaimDenied):
        await claim_story_with_credential(anon, account, **{**args, 'claim_credential': 'wrong'})
    assert await account.count_documents({}) == 0
    first = await claim_story_with_credential(anon, account, **args)
    assert first['playerState']['progress']['currentSceneId'] == 'forest'
    assert first['playerState']['bloodCoins'] == 0
    assert first['playerState']['achievements'] == {}
    assert 'premiumEntitlements' not in first['playerState']
    assert (await claim_story_with_credential(anon, account, **args))['_id'] == first['_id']
    assert await account.count_documents({}) == 1


@pytest.mark.asyncio
async def test_invalid_revision_is_not_disclosed_before_valid_proof(collections):
    anon, account = collections
    secret, digest = issue_claim_credential()
    wrong_secret, _ = issue_claim_credential()
    doc = anonymous_doc()
    doc['claimCredentialDigest'] = digest
    await anon.insert_one(doc)
    args = dict(authenticated_user_id='user-one', player_id='vc_abcdefgh',
                claim_credential=wrong_secret, now='now')
    for invalid_revision in (0, True, '2'):
        with pytest.raises(StoryClaimDenied):
            await claim_story_with_credential(
                anon, account, expected_anonymous_revision=invalid_revision, **args)
        with pytest.raises(StoryClaimConflict):
            await claim_story_with_credential(
                anon, account, expected_anonymous_revision=invalid_revision,
                **{**args, 'claim_credential': secret})
    assert await account.count_documents({}) == 0
    assert (await anon.find_one({'playerId': 'vc_abcdefgh'})).get('claimedBy') is None


@pytest.mark.asyncio
async def test_legacy_save_cannot_be_claimed_without_proof(collections):
    anon, account = collections
    await anon.insert_one(anonymous_doc())
    secret, _ = issue_claim_credential()
    with pytest.raises(StoryClaimDenied):
        await claim_story_with_credential(anon, account, authenticated_user_id='user-one',
            player_id='vc_abcdefgh', expected_anonymous_revision=2,
            claim_credential=secret, now='now')
    assert await account.count_documents({}) == 0
    assert 'claimedBy' not in await anon.find_one({'playerId': 'vc_abcdefgh'})


@pytest.mark.asyncio
async def test_rotated_proof_and_existing_account_fail_without_fence(collections):
    anon, account = collections
    old_secret, _ = issue_claim_credential()
    new_secret, new_digest = issue_claim_credential()
    doc = anonymous_doc()
    doc['claimCredentialDigest'] = new_digest
    await anon.insert_one(doc)
    args = dict(authenticated_user_id='user-one', player_id='vc_abcdefgh',
                expected_anonymous_revision=2, now='now')
    with pytest.raises(StoryClaimDenied):
        await claim_story_with_credential(anon, account, claim_credential=old_secret, **args)
    await account.insert_one({'userId': 'user-one', 'revision': 7})
    with pytest.raises(StoryClaimConflict):
        await claim_story_with_credential(anon, account, claim_credential=new_secret, **args)
    assert 'claimedBy' not in await anon.find_one({'playerId': 'vc_abcdefgh'})
