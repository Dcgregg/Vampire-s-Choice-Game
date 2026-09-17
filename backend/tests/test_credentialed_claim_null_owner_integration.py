"""Disposable MongoDB replica set only; never use a production TEST_MONGO_URI."""
import pytest

from progression.anonymous_claim_proof import issue_claim_credential
from progression.credentialed_story_claim import claim_story_with_credential
from test_story_claim_transaction_integration import collections  # noqa: F401
from test_story_claim_mongo_integration import anonymous_doc


@pytest.mark.asyncio
async def test_explicit_null_owner_is_claimable_with_valid_proof(collections):
    anonymous_saves, account_saves = collections
    secret, digest = issue_claim_credential()
    anonymous = anonymous_doc()
    anonymous['claimCredentialDigest'] = digest
    anonymous['claimedBy'] = None
    await anonymous_saves.insert_one(anonymous)

    claimed = await claim_story_with_credential(
        anonymous_saves, account_saves,
        authenticated_user_id='user-one', player_id='vc_abcdefgh',
        expected_anonymous_revision=2, claim_credential=secret, now='now',
    )

    assert claimed['userId'] == 'user-one'
    assert claimed['playerState']['bloodCoins'] == 0
    assert await account_saves.count_documents({'userId': 'user-one'}) == 1
    saved = await anonymous_saves.find_one({'playerId': 'vc_abcdefgh'})
    assert saved['claimedBy'] == 'user-one'
