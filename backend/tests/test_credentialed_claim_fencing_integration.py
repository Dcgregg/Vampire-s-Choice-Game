"""Credentialed claim fencing against disposable transaction-capable MongoDB only."""
import pytest

from progression.anonymous_claim_proof import issue_claim_credential
from progression.credentialed_story_claim import claim_story_with_credential
from progression.story_claim import StoryClaimConflict, StoryClaimDenied
from test_story_claim_transaction_integration import collections  # noqa: F401
from test_story_claim_mongo_integration import anonymous_doc


@pytest.mark.asyncio
async def test_stale_revision_does_not_claim_or_create_account_save(collections):
    anonymous, account = collections
    credential, digest = issue_claim_credential()
    doc = anonymous_doc(revision=3)
    doc['claimCredentialDigest'] = digest
    await anonymous.insert_one(doc)
    with pytest.raises(StoryClaimConflict):
        await claim_story_with_credential(
            anonymous, account, authenticated_user_id='account-one',
            player_id='vc_abcdefgh', expected_anonymous_revision=2,
            claim_credential=credential, now='now',
        )
    assert await account.count_documents({}) == 0
    assert 'claimedBy' not in await anonymous.find_one({'playerId': 'vc_abcdefgh'})


@pytest.mark.asyncio
async def test_claimed_save_denies_other_account_even_with_valid_credential(collections):
    anonymous, account = collections
    credential, digest = issue_claim_credential()
    doc = anonymous_doc()
    doc['claimCredentialDigest'] = digest
    await anonymous.insert_one(doc)
    common = dict(player_id='vc_abcdefgh', expected_anonymous_revision=2,
                  claim_credential=credential, now='now')
    first = await claim_story_with_credential(
        anonymous, account, authenticated_user_id='account-one', **common,
    )
    with pytest.raises(StoryClaimDenied):
        await claim_story_with_credential(
            anonymous, account, authenticated_user_id='account-two', **common,
        )
    assert await account.count_documents({}) == 1
    assert (await account.find_one({'userId': 'account-one'}))['_id'] == first['_id']
    assert await account.find_one({'userId': 'account-two'}) is None
    assert (await anonymous.find_one({'playerId': 'vc_abcdefgh'}))['claimedBy'] == 'account-one'
