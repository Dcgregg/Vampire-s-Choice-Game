"""Isolated route tests: no production credentials, MongoDB or live API wiring."""
from unittest.mock import AsyncMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from progression import story_claim_routes as routes
from progression.story_claim import StoryClaimConflict, StoryClaimDenied


async def verified_user():
    return {"user_id": "verified-account"}


def client(monkeypatch, outcome, *, ownership=True):
    service = AsyncMock(side_effect=outcome if isinstance(outcome, Exception) else None,
                        return_value=None if isinstance(outcome, Exception) else outcome)
    verifier = AsyncMock(return_value=ownership)
    monkeypatch.setattr(routes, "claim_story_only", service)
    app = FastAPI()
    app.include_router(routes.make_story_claim_router(object(), object(),
                                                     current_user=verified_user,
                                                     now=lambda: "2026-09-16T18:00:00Z",
                                                     verify_ownership=verifier))
    return TestClient(app), service, verifier


def payload():
    return {"playerId": "vc_abcdefgh", "expectedAnonymousRevision": 2}


def test_verified_identity_and_story_only_response(monkeypatch):
    save = {"_id": "private", "userId": "verified-account", "historicalAnonymousId": "vc_abcdefgh",
            "saveSchemaVersion": 3, "contentVersions": {},
            "playerState": {"progress": {"currentSceneId": "scene-two"}, "bloodCoins": 0},
            "revision": 1, "createdAt": "now", "updatedAt": "now"}
    http, service, verifier = client(monkeypatch, save)
    response = http.post("/api/me/claim-story-only", json={**payload(), "userId": "attacker"})
    assert response.status_code == 422
    assert service.await_count == 0 and verifier.await_count == 0
    response = http.post("/api/me/claim-story-only", json=payload())
    assert response.status_code == 200
    assert response.json()["playerState"]["progress"]["currentSceneId"] == "scene-two"
    assert "_id" not in response.json() and "userId" not in response.json()
    assert service.await_args.kwargs["authenticated_user_id"] == "verified-account"
    verifier.assert_awaited_once_with("vc_abcdefgh", "verified-account")


def test_conflict_never_overwrites_or_leaks_existing_save(monkeypatch):
    http, _, _ = client(monkeypatch, StoryClaimConflict("account already has a save; explicit choice required"))
    response = http.post("/api/me/claim-story-only", json=payload())
    assert response.status_code == 409
    assert "accountSave" not in response.text
    assert response.json()["detail"]["resolution"] == "review_existing_progress_or_retry"


def test_foreign_claim_does_not_expose_owner(monkeypatch):
    http, _, _ = client(monkeypatch, StoryClaimDenied("anonymous save belongs to another account"))
    response = http.post("/api/me/claim-story-only", json=payload())
    assert response.status_code == 403
    assert response.json() == {"detail": {"error": "claim_denied"}}


def test_invalid_revision_rejected_before_service(monkeypatch):
    http, service, verifier = client(monkeypatch, {})
    assert http.post("/api/me/claim-story-only", json={**payload(), "expectedAnonymousRevision": True}).status_code == 422
    assert service.await_count == 0 and verifier.await_count == 0


def test_auth_dependency_blocks_unauthenticated_claim(monkeypatch):
    http, service, _ = client(monkeypatch, {})
    async def denied():
        raise HTTPException(status_code=401, detail={"error": "not_authenticated"})
    app = FastAPI()
    app.include_router(routes.make_story_claim_router(object(), object(), current_user=denied,
                                                     now=lambda: "now"))
    response = TestClient(app).post("/api/me/claim-story-only", json=payload())
    assert response.status_code == 401
    assert service.await_count == 0


def test_missing_ownership_verifier_fails_closed(monkeypatch):
    http, service, _ = client(monkeypatch, {})
    app = FastAPI()
    app.include_router(routes.make_story_claim_router(object(), object(),
                                                     current_user=verified_user, now=lambda: "now"))
    response = TestClient(app).post("/api/me/claim-story-only", json=payload())
    assert response.status_code == 403
    assert response.json() == {"detail": {"error": "claim_denied"}}
    assert service.await_count == 0


def test_unverified_or_failed_ownership_never_calls_claim_service(monkeypatch):
    http, service, verifier = client(monkeypatch, {}, ownership=False)
    response = http.post("/api/me/claim-story-only", json=payload())
    assert response.status_code == 403
    assert response.json() == {"detail": {"error": "claim_denied"}}
    assert service.await_count == 0
    verifier.side_effect = RuntimeError("private verifier failure")
    response = http.post("/api/me/claim-story-only", json=payload())
    assert response.status_code == 403
    assert "private verifier failure" not in response.text
    assert service.await_count == 0
