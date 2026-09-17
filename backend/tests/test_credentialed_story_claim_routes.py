"""Isolated HTTP contract tests; no production services or player data."""
from unittest.mock import AsyncMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from progression import credentialed_story_claim_routes as routes
from progression.story_claim import StoryClaimConflict, StoryClaimDenied


async def authenticated():
    return {'user_id': 'account-from-session'}


def request():
    return {'playerId': 'vc_abcdefgh', 'expectedAnonymousRevision': 2}


def make_client(monkeypatch, outcome, identity=authenticated):
    service = AsyncMock(side_effect=outcome if isinstance(outcome, Exception) else None,
                        return_value=None if isinstance(outcome, Exception) else outcome)
    monkeypatch.setattr(routes, 'claim_story_with_credential', service)
    app = FastAPI()
    app.include_router(routes.make_credentialed_story_claim_router(
        object(), object(), current_user=identity, now=lambda: 'now'))
    return TestClient(app), service


def test_missing_credential_denied_without_service_call(monkeypatch):
    http, service = make_client(monkeypatch, {})
    response = http.post('/api/me/claim-story-with-credential', json=request())
    assert response.status_code == 403
    assert response.json() == {'detail': {'error': 'claim_denied'}}
    service.assert_not_awaited()


def test_verified_identity_and_credential_passed_to_transaction(monkeypatch):
    doc = {'_id': 'private', 'userId': 'account-from-session',
           'historicalAnonymousId': 'vc_abcdefgh', 'saveSchemaVersion': 3,
           'contentVersions': {}, 'playerState': {'bloodCoins': 0},
           'revision': 1, 'createdAt': 'now', 'updatedAt': 'now'}
    http, service = make_client(monkeypatch, doc)
    response = http.post('/api/me/claim-story-with-credential', json=request(),
                         headers={'X-Anonymous-Claim-Credential': 'secret-value'})
    assert response.status_code == 200
    assert response.json()['playerState']['bloodCoins'] == 0
    assert '_id' not in response.text and 'userId' not in response.text
    assert 'secret-value' not in response.text
    assert service.await_args.kwargs['authenticated_user_id'] == 'account-from-session'
    assert service.await_args.kwargs['claim_credential'] == 'secret-value'


def test_client_cannot_choose_identity_or_supply_extra_fields(monkeypatch):
    http, service = make_client(monkeypatch, {})
    response = http.post('/api/me/claim-story-with-credential',
                         json={**request(), 'userId': 'attacker'},
                         headers={'X-Anonymous-Claim-Credential': 'secret-value'})
    assert response.status_code == 422
    service.assert_not_awaited()


def test_denial_and_conflict_do_not_echo_secret(monkeypatch):
    for error, status in ((StoryClaimDenied('secret-value'), 403),
                          (StoryClaimConflict('secret-value'), 409)):
        http, _ = make_client(monkeypatch, error)
        response = http.post('/api/me/claim-story-with-credential', json=request(),
                             headers={'X-Anonymous-Claim-Credential': 'secret-value'})
        assert response.status_code == status
        assert 'secret-value' not in response.text
        assert 'accountSave' not in response.text


def test_authentication_dependency_blocks_claim(monkeypatch):
    async def unauthenticated():
        raise HTTPException(status_code=401, detail={'error': 'not_authenticated'})
    http, service = make_client(monkeypatch, {}, identity=unauthenticated)
    response = http.post('/api/me/claim-story-with-credential', json=request(),
                         headers={'X-Anonymous-Claim-Credential': 'secret-value'})
    assert response.status_code == 401
    service.assert_not_awaited()
