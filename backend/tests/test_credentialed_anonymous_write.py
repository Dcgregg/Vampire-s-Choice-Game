"""Isolated fake collection; never touches real player saves."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from progression.anonymous_claim_proof import issue_claim_credential
from progression.credentialed_anonymous_write import (
    AnonymousWriteConflict, AnonymousWriteDenied, write_credentialed_anonymous_save,
)


class Saves:
    def __init__(self, doc):
        self.doc = deepcopy(doc)
        self.before_update = None

    async def find_one(self, query):
        return deepcopy(self.doc) if self.doc and self.doc['playerId'] == query['playerId'] else None

    async def update_one(self, query, update):
        if self.before_update:
            self.before_update(self.doc)
        doc = self.doc
        matches = (doc and doc['playerId'] == query['playerId']
                   and doc['revision'] == query['revision']
                   and doc.get('claimCredentialDigest') == query['claimCredentialDigest']
                   and doc.get('claimedBy') is None)
        if not matches:
            return SimpleNamespace(matched_count=0)
        doc.update(deepcopy(update['$set']))
        doc['revision'] += update['$inc']['revision']
        return SimpleNamespace(matched_count=1)


def fixture():
    credential, digest = issue_claim_credential()
    doc = {'playerId': 'vc_' + 'a' * 32, 'claimCredentialDigest': digest,
           'saveSchemaVersion': 3, 'contentVersions': {},
           'playerState': {'progress': {}}, 'revision': 1,
           'createdAt': 'before', 'updatedAt': 'before'}
    state = {'progress': {'currentSceneId': 'chapter2'}, 'relationships': {},
             'flags': {}, 'settings': {}, 'version': 1, 'bloodCoins': 999,
             'achievements': {'forged': True}, 'dailyStreak': 42}
    return Saves(doc), credential, state


async def write(saves, credential, state, **changes):
    args = dict(player_id='vc_' + 'a' * 32, claim_credential=credential,
                expected_revision=1, player_state=state, now='after')
    args.update(changes)
    return await write_credentialed_anonymous_save(saves, **args)


@pytest.mark.asyncio
async def test_success_increments_revision_and_discards_rewards():
    saves, credential, state = fixture()
    result = await write(saves, credential, state)
    assert result['revision'] == saves.doc['revision'] == 2
    assert result['playerState']['progress']['currentSceneId'] == 'chapter2'
    assert result['playerState']['bloodCoins'] == 0
    assert result['playerState']['achievements'] == {}
    assert saves.doc['playerState']['dailyStreak'] == 0
    assert 'claimCredentialDigest' not in result and '_id' not in result
    assert 'claimCredentialDigest' in saves.doc


@pytest.mark.asyncio
async def test_wrong_proof_cross_id_and_legacy_fail_closed():
    saves, credential, state = fixture()
    for changes in ({'claim_credential': 'x' * 43},
                    {'claim_credential': ''},
                    {'player_id': 'vc_' + 'b' * 32}):
        with pytest.raises(AnonymousWriteDenied):
            await write(saves, credential, state, **changes)
    del saves.doc['claimCredentialDigest']
    with pytest.raises(AnonymousWriteDenied):
        await write(saves, credential, state)
    assert saves.doc['revision'] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('state', [None, {'progress': {}}, 'not a story'])
async def test_invalid_proof_is_denied_before_narrative_validation(state):
    saves, credential, _ = fixture()
    with pytest.raises(AnonymousWriteDenied):
        await write(saves, 'x' * 43, state, expected_revision=0)
    assert saves.doc['revision'] == 1
    assert saves.doc['playerState'] == {'progress': {}}


@pytest.mark.asyncio
async def test_claimed_and_stale_revision_are_rejected():
    saves, credential, state = fixture()
    saves.doc['claimedBy'] = 'user1'
    with pytest.raises(AnonymousWriteDenied):
        await write(saves, credential, state)
    del saves.doc['claimedBy']
    with pytest.raises(AnonymousWriteConflict):
        await write(saves, credential, state, expected_revision=2)
    assert saves.doc['revision'] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', [
    lambda doc: doc.update(claimedBy='user1'),
    lambda doc: doc.update(revision=2),
    lambda doc: doc.update(claimCredentialDigest='0' * 64),
])
async def test_claim_revision_or_credential_rotation_race_fails_cas(mutation):
    saves, credential, state = fixture()
    saves.before_update = mutation
    with pytest.raises(AnonymousWriteConflict):
        await write(saves, credential, state)
    assert saves.doc['playerState'] == {'progress': {}}


@pytest.mark.asyncio
async def test_invalid_narrative_does_not_write():
    saves, credential, state = fixture()
    with pytest.raises(AnonymousWriteConflict):
        await write(saves, credential, {'progress': {}})
    assert saves.doc['revision'] == 1
