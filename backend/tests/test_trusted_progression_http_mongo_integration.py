"""Authenticated HTTP -> trusted reducer -> disposable MongoDB full-book test.

This deliberately uses a test session cookie stored in disposable MongoDB. It
does not contact the external OAuth provider or production data.
"""
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException, Request
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

from progression.attributed_mongo_reservations import AttributedMongoReservationStore
from progression.feature_gated_routes import (
    OPENING_BOOK_ID, OPENING_CONTENT_VERSION, OPENING_SCENE_ID,
    register_trusted_progression_routes,
)
from progression.trusted_content import load_fixtures, load_registry


@pytest_asyncio.fixture
async def database():
    uri = os.environ.get("TEST_MONGO_URI")
    if not uri:
        pytest.skip("TEST_MONGO_URI required: never use production MongoDB")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    database = client[f"phase6c_http_progression_{uuid4().hex}"]
    try:
        await client.admin.command("ping")
        await AttributedMongoReservationStore(
            database.ledgers, database.events,
        ).ensure_indexes()
        await database.sessions.create_index("session_token", unique=True)
        yield database
    finally:
        await client.drop_database(database.name)
        client.close()


@pytest.mark.asyncio
async def test_session_cookie_completes_full_book_with_atomic_server_rewards(database):
    account_id = f"account-{uuid4().hex}"
    session_token = f"session-{uuid4().hex}"
    await database.sessions.insert_one({
        "session_token": session_token, "user_id": account_id,
    })

    async def current_user(request: Request):
        token = request.cookies.get("session_token")
        session = await database.sessions.find_one({"session_token": token})
        if session is None:
            raise HTTPException(status_code=401, detail={"error": "not_authenticated"})
        return {"user_id": session["user_id"]}

    app = FastAPI()
    assert register_trusted_progression_routes(
        app,
        activation_value="enabled",
        current_user=current_user,
        ledgers=database.ledgers,
        events=database.events,
        registry=load_registry(),
    ) is True
    headers = {
        "Cookie": f"session_token={session_token}",
        "X-VC-Progression": "1",
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test",
    ) as http:
        bootstrap = await http.post("/api/me/progression/bootstrap", headers=headers)
        assert bootstrap.status_code == 200, bootstrap.text
        initial = bootstrap.json()["ledger"]
        assert initial["coins"] == {"confirmed": 50}
        assert initial["achievements"] == {}
        assert initial["progressionRevision"] == 0

        lifecycle_id = str(uuid4())
        lifecycle = {
            "kind": "lifecycle", "eventId": lifecycle_id,
            "bookId": OPENING_BOOK_ID,
            "contentVersion": OPENING_CONTENT_VERSION,
            "baseProgressionRevision": 0,
            "lifecycleId": "character_created",
        }
        created = await http.post(
            "/api/me/progression/lifecycle", headers=headers, json=lifecycle,
        )
        assert created.status_code == 200, created.text
        ledger = created.json()["ledger"]
        assert ledger["progressionRevision"] == 1
        assert ledger["checkpoint"]["currentSceneId"] == OPENING_SCENE_ID
        assert ledger["achievements"]["THE_STORY_BEGINS"]["source"] == "awarded"
        assert type(ledger["achievements"]["THE_STORY_BEGINS"]["unlockedAt"]) is int

        fixture = load_fixtures()[0]
        last_event = None
        for step in fixture["steps"][1:]:
            last_event = {
                "kind": "choice", "eventId": str(uuid4()),
                "bookId": fixture["book"], "contentVersion": fixture["version"],
                "baseProgressionRevision": ledger["progressionRevision"],
                "fromSceneId": step["fromScene"], "choiceId": step["event"],
            }
            response = await http.post(
                "/api/me/progression/choices", headers=headers, json=last_event,
            )
            assert response.status_code == 200, response.text
            ledger = response.json()["ledger"]

        assert last_event is not None
        assert ledger["checkpoint"] == {
            "bookId": "book1", "contentVersion": 1,
            "currentSceneId": "b1_c3_s3", "terminal": True,
        }
        assert ledger["coins"] == {"confirmed": 370}
        assert set(ledger["achievements"]) == set(fixture["steps"][-1]["achievements"])

        duplicate = await http.post(
            "/api/me/progression/choices", headers=headers, json=last_event,
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["status"] == "duplicate"
        assert duplicate.json()["ledger"] == ledger

    stored = await database.ledgers.find_one({"ownerId": account_id})
    assert stored["coins"] == {"confirmed": 370}
    assert stored["checkpoint"]["terminal"] is True
    assert stored["lifecycleApplied"] == ["book1:1:character_created"]
    assert await database.ledgers.count_documents({"ownerId": account_id}) == 1
    assert await database.events.count_documents({"ledgerId": stored["_id"]}) == 12
