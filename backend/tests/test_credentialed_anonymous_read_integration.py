"""Credentialed read integration tests against disposable MongoDB only."""
import pytest

from progression.anonymous_claim_proof import issue_claim_credential
from progression.credentialed_anonymous_read import (
    AnonymousReadDenied, read_credentialed_anonymous_save,
)
from test_story_claim_transaction_integration import collections  # noqa: F401


@pytest.mark.asyncio
async def test_mongo_read_requires_matching_proof_and_returns_public_copy(collections):
    anonymous, _ = collections
    secret, digest = issue_claim_credential()
    await anonymous.insert_one({
        'playerId': 'vc_abcdefgh', 'claimCredentialDigest': digest,
        'saveSchemaVersion': 3, 'contentVersions': {'book1': 1},
        'playerState': {'progress': {'currentSceneId': 'forest'}},
        'revision': 2, 'createdAt': 'before', 'updatedAt': 'after',
    })
    for wrong in ('', 'x' * 43):
        with pytest.raises(AnonymousReadDenied):
            await read_credentialed_anonymous_save(
                anonymous, player_id='vc_abcdefgh', claim_credential=wrong,
            )
    with pytest.raises(AnonymousReadDenied):
        await read_credentialed_anonymous_save(
            anonymous, player_id='vc_other', claim_credential=secret,
        )
    result = await read_credentialed_anonymous_save(
        anonymous, player_id='vc_abcdefgh', claim_credential=secret,
    )
    assert result['revision'] == 2
    assert result['playerState']['progress']['currentSceneId'] == 'forest'
    assert 'claimCredentialDigest' not in result and '_id' not in result
    result['playerState']['progress']['currentSceneId'] = 'tampered'
    assert (await anonymous.find_one({'playerId': 'vc_abcdefgh'}))['playerState']['progress']['currentSceneId'] == 'forest'


@pytest.mark.asyncio
async def test_mongo_read_denies_claimed_legacy_and_rotated_proof(collections):
    anonymous, _ = collections
    old_secret, _ = issue_claim_credential()
    new_secret, digest = issue_claim_credential()
    await anonymous.insert_one({
        'playerId': 'vc_abcdefgh', 'claimCredentialDigest': digest,
        'revision': 1, 'claimedBy': 'account-one',
    })
    for proof in (old_secret, new_secret):
        with pytest.raises(AnonymousReadDenied):
            await read_credentialed_anonymous_save(
                anonymous, player_id='vc_abcdefgh', claim_credential=proof,
            )
    await anonymous.update_one({'playerId': 'vc_abcdefgh'}, {'$unset': {'claimedBy': ''}})
    with pytest.raises(AnonymousReadDenied):
        await read_credentialed_anonymous_save(
            anonymous, player_id='vc_abcdefgh', claim_credential=old_secret,
        )
    await anonymous.update_one({'playerId': 'vc_abcdefgh'}, {'$unset': {'claimCredentialDigest': ''}})
    with pytest.raises(AnonymousReadDenied):
        await read_credentialed_anonymous_save(
            anonymous, player_id='vc_abcdefgh', claim_credential=new_secret,
        )
