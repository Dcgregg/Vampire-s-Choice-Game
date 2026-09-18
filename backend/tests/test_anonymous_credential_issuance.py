"""Disposable in-memory collection only; no real player saves."""
from copy import deepcopy

import pytest
from pymongo.errors import DuplicateKeyError

from progression.anonymous_claim_proof import verify_claim_credential
from progression.anonymous_credential_issuance import (
    AnonymousCreationUnavailable, create_credentialed_anonymous_save,
)


class Saves:
    def __init__(self, failures=0):
        self.docs = []
        self.failures = failures

    async def insert_one(self, doc):
        if self.failures:
            self.failures -= 1
            raise DuplicateKeyError('duplicate playerId')
        self.docs.append(deepcopy(doc))
        doc['_id'] = 'internal-only'


def initial():
    return {'saveSchemaVersion': 3, 'contentVersions': {},
            'playerState': {'progress': {'currentSceneId': 'start'}}}


@pytest.mark.asyncio
async def test_new_save_uses_server_id_and_private_digest():
    saves = Saves()
    supplied = {**initial(), 'playerId': 'vc_attacker000',
                'claimCredentialDigest': 'attacker-controlled', 'revision': 900}
    public, secret = await create_credentialed_anonymous_save(
        saves, initial_save=supplied, now='now')
    assert public['playerId'].startswith('vc_')
    assert public['playerId'] != supplied['playerId']
    assert public['revision'] == 1
    assert 'claimCredentialDigest' not in public and '_id' not in public
    assert 'claimCredentialDigest' not in str(public)
    assert secret not in str(saves.docs)
    assert verify_claim_credential(saves.docs[0], secret)
    assert not verify_claim_credential(saves.docs[0], 'wrong')


@pytest.mark.asyncio
async def test_duplicate_retry_only_returns_credential_for_inserted_save():
    saves = Saves(failures=1)
    public, secret = await create_credentialed_anonymous_save(
        saves, initial_save=initial(), now='now')
    assert len(saves.docs) == 1
    assert verify_claim_credential(saves.docs[0], secret)
    assert public['playerId'] == saves.docs[0]['playerId']


@pytest.mark.asyncio
async def test_exhausted_insert_fails_without_issuing_identity():
    saves = Saves(failures=3)
    with pytest.raises(AnonymousCreationUnavailable):
        await create_credentialed_anonymous_save(
            saves, initial_save=initial(), now='now')
    assert saves.docs == []


@pytest.mark.asyncio
async def test_invalid_input_does_not_write():
    saves = Saves()
    with pytest.raises(ValueError):
        await create_credentialed_anonymous_save(
            saves, initial_save={'playerId': 'vc_attacker000'}, now='now')
    assert saves.docs == []


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', [
    {'saveSchemaVersion': True},
    {'saveSchemaVersion': 0},
    {'contentVersions': {'book1': True}},
    {'contentVersions': {'book1': 0}},
    {'contentVersions': []},
    {'playerState': []},
    {'playerState': {'bloodCoins': 50}},
    {'playerState': {'bloodCoins': False}},
    {'playerState': {'bloodCoins': '0'}},
    {'playerState': {'achievements': {'first': True}}},
    {'playerState': {'achievements': []}},
    {'playerState': {'dailyStreak': 1}},
    {'playerState': {'dailyStreak': False}},
    {'playerState': {'lastLoginDate': '2026-09-17'}},
    {'playerState': {'lastLoginDate': None}},
])
async def test_bad_initial_envelope_fails_before_insert(bad):
    saves = Saves()
    with pytest.raises(ValueError):
        await create_credentialed_anonymous_save(
            saves, initial_save={**initial(), **bad}, now='now')
    assert saves.docs == []
