"""HTTP contract tests for the unregistered account bootstrap route."""
from unittest.mock import AsyncMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from progression.account_progression_bootstrap import AccountProgressionUnavailable
from progression.account_progression_routes import make_account_progression_router

HEADERS = {"X-VC-Progression": "1"}

async def authenticated():
    return {"user_id": "account-from-session"}


def make_client(*, outcome=None, identity=authenticated):
    bootstrap = AsyncMock(
        side_effect=outcome if isinstance(outcome, Exception) else None,
        return_value={"ownerType": "account", "coins": {"confirmed": 50},
                      "achievements": {}, "checkpoint": {
                          "bookId": "book1", "contentVersion": 1,
                          "currentSceneId": "start", "terminal": False},
                      "progressionRevision": 0},
    )
    app = FastAPI()
    app.include_router(make_account_progression_router(
        current_user=identity, bootstrap=bootstrap,
    ))
    return TestClient(app), bootstrap


def test_bootstrap_uses_session_identity_and_accepts_no_client_state():
    http, bootstrap = make_client()
    response = http.post("/api/me/progression/bootstrap", headers=HEADERS, json={
        "ownerId": "attacker", "bloodCoins": 999999, "achievements": {"all": True},
    })
    assert response.status_code == 200
    assert response.json()["ledger"]["coins"] == {"confirmed": 50}
    assert bootstrap.await_args.kwargs == {
        "authenticated_user_id": "account-from-session",
    }
    assert response.headers["cache-control"] == "no-store"
    assert "attacker" not in response.text


def test_authentication_blocks_bootstrap():
    async def unauthenticated():
        raise HTTPException(status_code=401, detail={"error": "not_authenticated"})
    http, bootstrap = make_client(identity=unauthenticated)
    assert http.post("/api/me/progression/bootstrap").status_code == 401
    bootstrap.assert_not_awaited()


def test_bootstrap_failure_is_stable_and_private():
    http, _ = make_client(outcome=AccountProgressionUnavailable("private database detail"))
    response = http.post("/api/me/progression/bootstrap", headers=HEADERS)
    assert response.status_code == 503
    assert response.json() == {"detail": {
        "error": "progression_bootstrap_unavailable", "retryable": False,
    }}
    assert "private" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_bootstrap_rejects_cross_site_form_shape_without_csrf_header():
    http, bootstrap = make_client()
    response = http.post("/api/me/progression/bootstrap")
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "csrf_check_failed"
    bootstrap.assert_not_awaited()
