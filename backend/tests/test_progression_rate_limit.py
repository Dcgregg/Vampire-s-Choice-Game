from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from progression.rate_limit import AccountRateLimiter
from progression.trusted_progression_routes import make_trusted_progression_router


def test_enabled_route_limiter_is_account_scoped_and_returns_stable_429():
    now = [100.0]
    limiter = AccountRateLimiter(
        limit=2, window_seconds=60, clock=lambda: now[0],
    )
    service = AsyncMock(return_value={"status": "confirmed", "eventId": "x"})

    async def user():
        return {"user_id": "account-a"}

    app = FastAPI()
    app.include_router(make_trusted_progression_router(
        current_user=user, process_choice=service, rate_limiter=limiter,
    ))
    http = TestClient(app)
    headers = {"X-VC-Progression": "1"}
    event = {"kind": "choice",
             "eventId": "550e8400-e29b-41d4-a716-446655440000",
             "bookId": "book1", "contentVersion": 1,
             "baseProgressionRevision": 0, "fromSceneId": "start",
             "choiceId": "ordinary"}
    assert http.post("/api/me/progression/choices", headers=headers, json=event).status_code == 200
    event["eventId"] = "550e8400-e29b-41d4-a716-446655440001"
    assert http.post("/api/me/progression/choices", headers=headers, json=event).status_code == 200
    event["eventId"] = "550e8400-e29b-41d4-a716-446655440002"
    limited = http.post("/api/me/progression/choices", headers=headers, json=event)
    assert limited.status_code == 429
    assert limited.json()["detail"] == {
        "error": "progression_rate_limited", "retryable": True,
    }
    assert limited.headers["retry-after"] == "61"

    now[0] = 161.0
    assert http.post("/api/me/progression/choices", headers=headers, json=event).status_code == 200
