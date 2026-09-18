"""Disposable MongoDB only; never point TEST_MONGO_URI at production."""
import pytest

from progression.anonymous_claim_proof import issue_claim_credential
from progression.credentialed_anonymous_write import (
    AnonymousWriteConflict, AnonymousWriteDenied, write_credentialed_anonymous_save,
)
from test_story_claim_transaction_integration import collections  # noqa: F401


@pytest.mark.asyncio
async def test_real_mongo_write_cas_and_reward_scrubbing(collections):
    anon, _ = collections
    secret, digest = issue_claim_credential()
    await anon.insert_one({
        'playerId': 'vc_abcdefgh', 'claimCredentialDigest': digest,
        'saveSchemaVersion': 3, 'contentVersions': {}, 'revision': 1,
        'playerState': {'progress': {}}, 'createdAt': 'before', 'updatedAt': 'before',
    })
    state = {'progress': {'currentSceneId': 'forest'}, 'relationships': {},
             'flags': {}, 'settings': {}, 'version': 1, 'bloodCoins': 900,
             'achievements': {'forged': True}, 'dailyStreak': 20}
    args = dict(player_id='vc_abcdefgh', claim_credential=secret,
                expected_revision=1, player_state=state, now='after')
    with pytest.raises(AnonymousWriteDenied):
        await write_credentialed_anonymous_save(anon, **{**args, 'claim_credential': 'x' * 43})
    public = await write_credentialed_anonymous_save(anon, **args)
    stored = await anon.find_one({'playerId': 'vc_abcdefgh'})
    assert public['revision'] == stored['revision'] == 2
    assert public['playerState']['bloodCoins'] == stored['playerState']['bloodCoins'] == 0
    assert stored['playerState']['achievements'] == {}
    assert stored['playerState']['dailyStreak'] == 0
    assert stored['claimCredentialDigest'] == digest
    assert 'claimCredentialDigest' not in public and '_id' not in public
    with pytest.raises(AnonymousWriteConflict):
        await write_credentialed_anonymous_save(anon, **args)
    assert (await anon.find_one({'playerId': 'vc_abcdefgh'}))['revision'] == 2


@pytest.mark.asyncio
async def test_real_mongo_claimed_and_legacy_saves_fail_closed(collections):
    anon, _ = collections
    secret, digest = issue_claim_credential()
    state = {'progress': {}, 'relationships': {}, 'flags': {}, 'settings': {}, 'version': 1}
    args = dict(player_id='vc_abcdefgh', claim_credential=secret,
                expected_revision=1, player_state=state, now='after')
    await anon.insert_one({'playerId': 'vc_abcdefgh', 'claimCredentialDigest': digest,
                           'revision': 1, 'claimedBy': 'user-one'})
    with pytest.raises(AnonymousWriteDenied):
        await write_credentialed_anonymous_save(anon, **args)
    await anon.delete_one({'playerId': 'vc_abcdefgh'})
    await anon.insert_one({'playerId': 'vc_abcdefgh', 'revision': 1})
    with pytest.raises(AnonymousWriteDenied):
        await write_credentialed_anonymous_save(anon, **args)
