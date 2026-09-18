"""Isolated in-memory read tests; no live player data or routes."""
from copy import deepcopy

import pytest

from progression.anonymous_claim_proof import issue_claim_credential
from progression.credentialed_anonymous_read import (
    AnonymousReadDenied, read_credentialed_anonymous_save,
)


class Saves:
    def __init__(self, doc):
        self.doc = doc
        self.lookups = []

    async def find_one(self, query):
        self.lookups.append(query)
        if self.doc is not None and self.doc['playerId'] == query['playerId']:
            return deepcopy(self.doc)
        return None


def fixture():
    credential, digest = issue_claim_credential()
    doc = {'_id': 'private', 'playerId': 'vc_abcdefgh',
           'claimCredentialDigest': digest, 'saveSchemaVersion': 3,
           'contentVersions': {}, 'playerState': {'progress': {'scene': 'start'}},
           'revision': 1, 'createdAt': 'now', 'updatedAt': 'now'}
    return Saves(doc), credential


@pytest.mark.asyncio
async def test_matching_proof_returns_only_public_envelope_and_copy():
    saves, credential = fixture()
    result = await read_credentialed_anonymous_save(
        saves, player_id='vc_abcdefgh', claim_credential=credential)
    assert result['playerId'] == 'vc_abcdefgh'
    assert '_id' not in result and 'claimCredentialDigest' not in result
    assert credential not in str(result)
    result['playerState']['progress']['scene'] = 'changed'
    assert saves.doc['playerState']['progress']['scene'] == 'start'


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['missing', 'wrong', 'malformed', 'legacy', 'claimed', 'other_id'])
async def test_denied_cases_do_not_disclose_save(case):
    saves, credential = fixture()
    player_id = 'vc_abcdefgh'
    if case == 'missing':
        credential = None
    elif case == 'wrong':
        credential, _ = issue_claim_credential()
    elif case == 'malformed':
        credential = 'not-a-proof'
    elif case == 'legacy':
        del saves.doc['claimCredentialDigest']
    elif case == 'claimed':
        saves.doc['claimedBy'] = 'some-account'
    else:
        player_id = 'vc_other123'
    with pytest.raises(AnonymousReadDenied):
        await read_credentialed_anonymous_save(
            saves, player_id=player_id, claim_credential=credential)


@pytest.mark.asyncio
async def test_invalid_locator_does_not_query_database():
    saves, credential = fixture()
    with pytest.raises(AnonymousReadDenied):
        await read_credentialed_anonymous_save(
            saves, player_id='invalid', claim_credential=credential)
    assert saves.lookups == []
