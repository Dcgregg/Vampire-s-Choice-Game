"""Disposable-Mongo regression for the unregistered write -> claim primitives.

This does not validate story-choice eligibility or exercise production routes.
"""
import pytest

from progression.anonymous_credential_issuance import create_credentialed_anonymous_save
from progression.credentialed_anonymous_write import (
    AnonymousWriteConflict, AnonymousWriteDenied, write_credentialed_anonymous_save,
)
from progression.credentialed_story_claim import claim_story_with_credential
from progression.story_claim import StoryClaimConflict
from test_story_claim_transaction_integration import collections  # noqa: F401
from test_story_claim_mongo_integration import anonymous_doc


@pytest.mark.asyncio
async def test_credentialed_write_then_claim_retains_story_but_not_forged_rewards(collections):
    anonymous_saves, account_saves = collections
    seed = anonymous_doc()
    initial = {key: seed[key] for key in ('saveSchemaVersion', 'contentVersions', 'playerState')}
    initial['playerState']['bloodCoins'] = 0
    initial['playerState']['achievements'] = {}
    initial['playerState']['dailyStreak'] = 0
    initial['playerState']['lastLoginDate'] = ''
    issued, secret = await create_credentialed_anonymous_save(
        anonymous_saves, initial_save=initial, now='issued')
    player_id = issued['playerId']
    forged = {**issued['playerState'], 'bloodCoins': 99999,
              'achievements': {'forged': True}, 'dailyStreak': 500,
              'lastLoginDate': 'forged'}
    forged['progress'] = {**forged['progress'], 'currentSceneId': 'forest'}
    written = await write_credentialed_anonymous_save(
        anonymous_saves, player_id=player_id, claim_credential=secret,
        expected_revision=1, player_state=forged, now='written')
    assert written['revision'] == 2
    assert written['playerState']['progress']['currentSceneId'] == 'forest'
    assert written['playerState']['bloodCoins'] == 0
    assert written['playerState']['achievements'] == {}
    assert written['playerState']['dailyStreak'] == 0
    assert written['playerState']['lastLoginDate'] == ''

    with pytest.raises(StoryClaimConflict):
        await claim_story_with_credential(
            anonymous_saves, account_saves, authenticated_user_id='chain-account',
            player_id=player_id, expected_anonymous_revision=1,
            claim_credential=secret, now='claimed')
    assert await account_saves.count_documents({'userId': 'chain-account'}) == 0
    claimed = await claim_story_with_credential(
        anonymous_saves, account_saves, authenticated_user_id='chain-account',
        player_id=player_id, expected_anonymous_revision=2,
        claim_credential=secret, now='claimed')
    assert claimed['playerState']['progress'] == written['playerState']['progress']
    assert claimed['playerState']['bloodCoins'] == 0
    assert claimed['playerState']['achievements'] == {}
    assert claimed['playerState']['dailyStreak'] == 0
    assert claimed['playerState']['lastLoginDate'] == ''
    assert await account_saves.count_documents({'userId': 'chain-account'}) == 1
    with pytest.raises(AnonymousWriteDenied):
        await write_credentialed_anonymous_save(
            anonymous_saves, player_id=player_id, claim_credential=secret,
            expected_revision=2, player_state=forged, now='too-late')
    assert (await anonymous_saves.find_one({'playerId': player_id}))['revision'] == 2
