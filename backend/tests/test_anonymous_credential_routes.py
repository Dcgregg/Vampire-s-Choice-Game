"""No live server or production database: issuance route contract tests."""
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from progression import anonymous_credential_routes as routes
from progression.anonymous_credential_issuance import AnonymousCreationUnavailable


def test_new_identity_is_server_initialised_and_secret_is_not_cached(monkeypatch):
    service = AsyncMock(return_value=({'playerId': 'vc_server_generated', 'revision': 1,
                                       'playerState': {}, 'saveSchemaVersion': 3,
                                       'contentVersions': {}, 'createdAt': 'now',
                                       'updatedAt': 'now'}, 'one-time-secret'))
    monkeypatch.setattr(routes, 'create_credentialed_anonymous_save', service)
    app = FastAPI()
    app.include_router(routes.make_anonymous_credential_router(
        object(), initial_save=lambda: {'saveSchemaVersion': 3, 'contentVersions': {},
                                        'playerState': {}}, now=lambda: 'now'))
    response = TestClient(app).post('/api/anonymous/credentialed-save')
    assert response.status_code == 201
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['pragma'] == 'no-cache'
    assert response.json()['claimCredential'] == 'one-time-secret'
    assert 'claimCredentialDigest' not in response.text
    assert service.await_args.kwargs['initial_save']['playerState'] == {}
    assert TestClient(app).post('/api/anonymous/credentialed-save',
                                json={'playerId': 'vc_attacker', 'playerState': {'bloodCoins': 999}}).status_code == 201
    assert service.await_count == 2
    assert service.await_args.kwargs['initial_save']['playerState'] == {}


def test_failed_insert_never_delivers_a_credential(monkeypatch):
    service = AsyncMock(side_effect=AnonymousCreationUnavailable('private database error'))
    monkeypatch.setattr(routes, 'create_credentialed_anonymous_save', service)
    app = FastAPI()
    app.include_router(routes.make_anonymous_credential_router(
        object(), initial_save=lambda: {'saveSchemaVersion': 3, 'contentVersions': {},
                                        'playerState': {}}, now=lambda: 'now'))
    response = TestClient(app).post('/api/anonymous/credentialed-save')
    assert response.status_code == 503
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['pragma'] == 'no-cache'
    assert response.json() == {'detail': {'error': 'creation_unavailable'}}
    assert 'private database error' not in response.text
    assert 'claimCredential' not in response.text
