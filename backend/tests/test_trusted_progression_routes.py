"""Strict HTTP contract tests for the unregistered trusted-choice router."""
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from progression.strict_event_input import StrictChoiceEvent
from progression.trusted_choice_service import (
    TrustedChoiceConflict, TrustedChoiceIndeterminate, TrustedChoiceUnavailable,
    TrustedChoiceValidationError,
)
from progression.trusted_progression_routes import make_trusted_progression_router


EVENT_ID = "550e8400-e29b-41d4-a716-446655440000"


def event(**changes):
    body = {"kind": "choice", "eventId": EVENT_ID, "bookId": "book1",
            "contentVersion": 1, "baseProgressionRevision": 0,
            "fromSceneId": "start", "choiceId": "ordinary"}
    body.update(changes)
    return body


async def authenticated():
    return {"user_id": "account-from-session"}


def client(outcome=None, *, identity=authenticated):
    service = AsyncMock(
        side_effect=outcome if isinstance(outcome, Exception) else None,
        return_value=outcome if isinstance(outcome, dict) else {
            "status": "confirmed", "eventId": EVENT_ID,
            "ledger": {"ownerType": "account", "coins": {"confirmed": 50},
                       "achievements": {}, "checkpoint": {
                           "bookId": "book1", "contentVersion": 1,
                           "currentSceneId": "next", "terminal": False},
                       "progressionRevision": 1},
        },
    )
    app = FastAPI()
    app.include_router(make_trusted_progression_router(
        current_user=identity, process_choice=service,
    ))
    return TestClient(app), service


def test_verified_session_identity_is_the_only_owner_input():
    http, service = client()
    response = http.post("/api/me/progression/choices", json=event())
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.json()["ledger"]["coins"]["confirmed"] == 50
    assert service.await_args.kwargs["authenticated_user_id"] == "account-from-session"
    assert isinstance(service.await_args.kwargs["event"], StrictChoiceEvent)
    assert "ownerId" not in response.text and "_id" not in response.text


@pytest.mark.parametrize("extra", [
    {"ownerId": "attacker"}, {"ledgerId": "foreign"}, {"coins": 999},
    {"awards": {"coins": 999}}, {"projection": {}},
])
def test_untrusted_fields_are_rejected_before_service(extra):
    http, service = client()
    response = http.post("/api/me/progression/choices", json=event(**extra))
    assert response.status_code == 422
    service.assert_not_awaited()


def test_authentication_dependency_blocks_choice():
    async def unauthenticated():
        raise HTTPException(status_code=401, detail={"error": "not_authenticated"})
    http, service = client(identity=unauthenticated)
    assert http.post("/api/me/progression/choices", json=event()).status_code == 401
    service.assert_not_awaited()


@pytest.mark.parametrize("error,status,code", [
    (TrustedChoiceUnavailable("private"), 404, "progression_unavailable"),
    (TrustedChoiceValidationError("private"), 422, "invalid_choice"),
    (TrustedChoiceConflict("private"), 409, "progression_conflict"),
    (TrustedChoiceIndeterminate("private"), 503, "progression_indeterminate"),
])
def test_stable_errors_do_not_expose_internal_details(error, status, code):
    http, _ = client(error)
    response = http.post("/api/me/progression/choices", json=event())
    assert response.status_code == status
    assert response.json()["detail"]["error"] == code
    assert "private" not in response.text
    assert response.headers["cache-control"] == "no-store"
