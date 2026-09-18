"""Inert HTTP-to-Mongo claim integration; TEST_MONGO_URI must be disposable.

This mounts only experimental routers in a test FastAPI app. It does not
register routes in the live server or exercise a real browser/login session.
"""
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from progression.anonymous_claim_proof import issue_claim_credential
from progression.anonymous_credential_routes import make_anonymous_credential_router
from progression.credentialed_story_claim_routes import make_credentialed_story_claim_router
from test_story_claim_transaction_integration import collections  # noqa: F401
from test_story_claim_mongo_integration import anonymous_doc


async def authenticated():
    return {'user_id': 'test-account'}


@pytest.mark.asyncio
async def test_http_claim_checks_proof_in_real_transaction_and_strips_rewards(collections):
    anonymous_saves, account_saves = collections
    secret, digest = issue_claim_credential()
    original = anonymous_doc()
    original['claimCredentialDigest'] = digest
    original['playerState']['bloodCoins'] = 999999
    original['playerState']['achievements'] = {'forged': True}
    await anonymous_saves.insert_one(original)

    app = FastAPI()
    app.include_router(make_credentialed_story_claim_router(
        anonymous_saves, account_saves, current_user=authenticated, now=lambda: 'now'))
    payload = {'playerId': original['playerId'],
               'expectedAnonymousRevision': original['revision']}
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as http:
        denied = await http.post('/api/me/claim-story-with-credential', json=payload,
                                 headers={'X-Anonymous-Claim-Credential': 'A' * 43})
        assert denied.status_code == 403
        assert denied.headers['cache-control'] == 'no-store'
        assert await account_saves.count_documents({}) == 0
        assert (await anonymous_saves.find_one({'playerId': original['playerId']})).get('claimedBy') is None

        claimed = await http.post('/api/me/claim-story-with-credential', json=payload,
                                  headers={'X-Anonymous-Claim-Credential': secret})
        assert claimed.status_code == 200, claimed.text
        body = claimed.json()
        assert body['playerState']['progress']['currentSceneId'] == 'forest'
        assert body['playerState']['bloodCoins'] == 0
        assert body['playerState']['achievements'] == {}
        assert claimed.headers['cache-control'] == 'no-store'
        assert secret not in claimed.text and digest not in claimed.text
        assert '_id' not in body and 'userId' not in body

        repeat = await http.post('/api/me/claim-story-with-credential', json=payload,
                                 headers={'X-Anonymous-Claim-Credential': secret})
        assert repeat.status_code == 200
        assert repeat.json() == body
    assert await account_saves.count_documents({'userId': 'test-account'}) == 1
    assert (await anonymous_saves.find_one({'playerId': original['playerId']}))['claimedBy'] == 'test-account'


@pytest.mark.asyncio
async def test_http_claim_cannot_transfer_already_claimed_story_to_second_account(collections):
    anonymous_saves, account_saves = collections
    secret, digest = issue_claim_credential()
    original = anonymous_doc()
    original['claimCredentialDigest'] = digest
    await anonymous_saves.insert_one(original)
    payload = {'playerId': original['playerId'],
               'expectedAnonymousRevision': original['revision']}
    headers = {'X-Anonymous-Claim-Credential': secret}

    async def first_identity():
        return {'user_id': 'first-account'}

    async def second_identity():
        return {'user_id': 'second-account'}

    first_app = FastAPI()
    first_app.include_router(make_credentialed_story_claim_router(
        anonymous_saves, account_saves, current_user=first_identity, now=lambda: 'now'))
    second_app = FastAPI()
    second_app.include_router(make_credentialed_story_claim_router(
        anonymous_saves, account_saves, current_user=second_identity, now=lambda: 'later'))

    async with AsyncClient(transport=ASGITransport(app=first_app), base_url='http://first') as first:
        claimed = await first.post('/api/me/claim-story-with-credential', json=payload, headers=headers)
        assert claimed.status_code == 200, claimed.text
    async with AsyncClient(transport=ASGITransport(app=second_app), base_url='http://second') as second:
        denied = await second.post('/api/me/claim-story-with-credential', json=payload, headers=headers)
        assert denied.status_code == 403
        assert denied.headers['cache-control'] == 'no-store'
        assert secret not in denied.text
    assert await account_saves.count_documents({'userId': 'first-account'}) == 1
    assert await account_saves.count_documents({'userId': 'second-account'}) == 0
    assert (await anonymous_saves.find_one({'playerId': original['playerId']}))['claimedBy'] == 'first-account'


@pytest.mark.asyncio
async def test_http_issuance_to_claim_uses_server_generated_identity_and_disposable_mongo(collections):
    anonymous_saves, account_saves = collections
    seed = anonymous_doc()
    initial = {key: seed[key] for key in ('saveSchemaVersion', 'contentVersions', 'playerState')}
    initial['playerState']['bloodCoins'] = 0
    initial['playerState']['achievements'] = {}
    initial['playerState']['dailyStreak'] = 0
    initial['playerState']['lastLoginDate'] = ''
    app = FastAPI()
    app.include_router(make_anonymous_credential_router(
        anonymous_saves, initial_save=lambda: initial, now=lambda: 'issued'))
    app.include_router(make_credentialed_story_claim_router(
        anonymous_saves, account_saves, current_user=authenticated, now=lambda: 'claimed'))
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as http:
        issued = await http.post('/api/anonymous/credentialed-save', json={})
        assert issued.status_code == 201, issued.text
        assert issued.headers['cache-control'] == 'no-store'
        public = issued.json()['save']
        credential = issued.json()['claimCredential']
        assert public['playerId'].startswith('vc_')
        assert public['revision'] == 1
        assert '_id' not in public and 'claimCredentialDigest' not in public
        stored = await anonymous_saves.find_one({'playerId': public['playerId']})
        assert stored is not None and stored['claimCredentialDigest'] != credential
        payload = {'playerId': public['playerId'], 'expectedAnonymousRevision': public['revision']}
        claimed = await http.post('/api/me/claim-story-with-credential', json=payload,
                                  headers={'X-Anonymous-Claim-Credential': credential})
        assert claimed.status_code == 200, claimed.text
        assert claimed.json()['playerState']['progress'] == public['playerState']['progress']
        assert claimed.json()['playerState']['bloodCoins'] == 0
        assert claimed.json()['playerState']['achievements'] == {}
        assert credential not in claimed.text and stored['claimCredentialDigest'] not in claimed.text
    assert await account_saves.count_documents({'userId': 'test-account'}) == 1
    assert (await anonymous_saves.find_one({'playerId': public['playerId']}))['claimedBy'] == 'test-account'
