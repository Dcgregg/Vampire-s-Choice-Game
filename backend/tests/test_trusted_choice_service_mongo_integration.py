"""Disposable-Mongo end-to-end tests for authenticated trusted choices.

These tests use only TEST_MONGO_URI and must never point at production data.
They exercise the service, durable reservation adapter and transaction-backed
ledger together rather than mocking the persistence boundary.
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from progression.attributed_mongo_reservations import AttributedMongoReservationStore
from progression.strict_event_input import StrictChoiceEvent
from progression.trusted_choice_reservation import plan_account_choice_reservation
from progression.trusted_choice_service import (
    TrustedChoiceConflict,
    TrustedChoiceIndeterminate,
    process_account_choice,
)


def registry():
    return {
        "characters": {"friend": 0},
        "rules": {
            "affinityMin": -100,
            "affinityMax": 100,
            "coinsMin": 0,
            "derivedAchievements": [],
        },
        "books": {"book1": {"version": 1, "scenes": {
            "start": {"choices": {
                "ordinary": {
                    "nextSceneId": "next",
                    "effects": {"coinsChange": 10},
                },
                "alternate": {
                    "nextSceneId": "next",
                    "effects": {"coinsChange": 20},
                },
            }},
            "next": {"choices": {}},
        }}},
    }


def choice(event_id=None, *, choice_id="ordinary"):
    return StrictChoiceEvent(
        kind="choice",
        eventId=event_id or str(uuid4()),
        bookId="book1",
        contentVersion=1,
        baseProgressionRevision=0,
        fromSceneId="start",
        choiceId=choice_id,
    )


@pytest_asyncio.fixture
async def database():
    uri = os.environ.get("TEST_MONGO_URI")
    if not uri:
        pytest.skip("TEST_MONGO_URI required: never use production MongoDB")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    db = client[f"phase6c_choice_service_{uuid4().hex}"]
    try:
        await client.admin.command("ping")
        await AttributedMongoReservationStore(db.ledgers, db.events).ensure_indexes()
        yield db
    finally:
        await client.drop_database(db.name)
        client.close()


async def seed_account(database, owner_id=None):
    owner_id = owner_id or f"account-{uuid4().hex}"
    ledger = {
        "_id": uuid4().hex,
        "ownerType": "account",
        "ownerId": owner_id,
        "progressionRevision": 0,
        "appliedEventIds": {},
        "checkpoint": {
            "bookId": "book1",
            "contentVersion": 1,
            "currentSceneId": "start",
            "terminal": False,
        },
        "coins": {"confirmed": 50},
        "achievements": {},
        "derived": {
            "coins": 50,
            "affinity": {"friend": 0},
            "flags": {},
            "achievements": [],
        },
        "openingGranted": True,
    }
    await database.ledgers.insert_one(ledger)
    return owner_id, ledger


async def process(database, owner_id, event):
    return await process_account_choice(
        database.ledgers,
        database.events,
        registry(),
        authenticated_user_id=owner_id,
        event=event,
    )


@pytest.mark.asyncio
async def test_confirmed_choice_and_identical_retry_award_once(database):
    owner_id, ledger = await seed_account(database)
    event = choice()

    first = await process(database, owner_id, event)
    duplicate = await process(database, owner_id, event)

    assert first["status"] == "confirmed"
    assert duplicate["status"] == "duplicate"
    assert first["ledger"] == duplicate["ledger"]
    assert duplicate["ledger"]["coins"] == {"confirmed": 60}
    assert duplicate["ledger"]["progressionRevision"] == 1
    stored = await database.ledgers.find_one({"_id": ledger["_id"]})
    assert stored["appliedEventIds"] == {"1": event.eventId}
    assert await database.events.count_documents({
        "ledgerId": ledger["_id"], "eventId": event.eventId,
    }) == 1


@pytest.mark.asyncio
async def test_reused_event_id_with_changed_choice_never_changes_state(database):
    owner_id, ledger = await seed_account(database)
    event = choice()
    await process(database, owner_id, event)

    with pytest.raises(TrustedChoiceConflict, match="different intent"):
        await process(
            database,
            owner_id,
            choice(event.eventId, choice_id="alternate"),
        )

    stored = await database.ledgers.find_one({"_id": ledger["_id"]})
    assert stored["progressionRevision"] == 1
    assert stored["coins"] == {"confirmed": 60}
    assert stored["appliedEventIds"] == {"1": event.eventId}


@pytest.mark.asyncio
async def test_concurrent_identical_requests_award_exactly_once(database):
    owner_id, ledger = await seed_account(database)
    event = choice()

    results = await asyncio.gather(
        *(process(database, owner_id, event) for _ in range(12)),
        return_exceptions=True,
    )

    successes = [result for result in results if isinstance(result, dict)]
    assert sum(result["status"] == "confirmed" for result in successes) == 1
    assert all(
        isinstance(result, dict) or isinstance(result, TrustedChoiceIndeterminate)
        for result in results
    ), results
    stored = await database.ledgers.find_one({"_id": ledger["_id"]})
    assert stored["progressionRevision"] == 1
    assert stored["coins"] == {"confirmed": 60}
    assert stored["appliedEventIds"] == {"1": event.eventId}
    assert await database.events.count_documents({"ledgerId": ledger["_id"]}) == 1


@pytest.mark.asyncio
async def test_concurrent_different_events_can_reserve_revision_once(database):
    owner_id, ledger = await seed_account(database)
    events = [choice() for _ in range(12)]

    results = await asyncio.gather(
        *(process(database, owner_id, event) for event in events),
        return_exceptions=True,
    )

    successes = [result for result in results if isinstance(result, dict)]
    assert len(successes) == 1
    assert successes[0]["status"] == "confirmed"
    assert all(
        isinstance(result, dict) or isinstance(result, TrustedChoiceConflict)
        for result in results
    ), results
    stored = await database.ledgers.find_one({"_id": ledger["_id"]})
    assert stored["progressionRevision"] == 1
    assert stored["coins"] == {"confirmed": 60}
    assert len(stored["appliedEventIds"]) == 1
    assert await database.events.count_documents({
        "ledgerId": ledger["_id"], "targetRevision": 1,
    }) == 1


@pytest.mark.asyncio
async def test_retry_reconciles_commit_before_finalisation(database):
    owner_id, ledger = await seed_account(database)
    event = choice()
    store = AttributedMongoReservationStore(database.ledgers, database.events)
    plan = plan_account_choice_reservation(
        registry(), ledger, event, authenticated_user_id=owner_id,
    )
    reserved = await store.reserve(**plan)
    await store.commit(event=reserved, lease_owner=reserved["leaseOwner"])
    pending = await database.events.find_one({"_id": reserved["_id"]})
    assert pending["status"] == "committing"

    recovered = await process(database, owner_id, event)

    assert recovered["status"] == "duplicate"
    assert recovered["ledger"]["coins"] == {"confirmed": 60}
    assert recovered["ledger"]["progressionRevision"] == 1
    applied = await database.events.find_one({"_id": reserved["_id"]})
    assert applied["status"] == "applied"
    assert applied["resultRevision"] == 1


@pytest.mark.asyncio
async def test_active_unknown_outcome_fails_closed_then_expired_retry_recovers(database):
    owner_id, ledger = await seed_account(database)
    event = choice()
    store = AttributedMongoReservationStore(database.ledgers, database.events)
    reserved = await store.reserve(**plan_account_choice_reservation(
        registry(), ledger, event, authenticated_user_id=owner_id,
    ))

    with pytest.raises(TrustedChoiceIndeterminate, match="reconciled"):
        await process(database, owner_id, event)
    unchanged = await database.ledgers.find_one({"_id": ledger["_id"]})
    assert unchanged["progressionRevision"] == 0
    assert unchanged["coins"] == {"confirmed": 50}

    await database.events.update_one(
        {"_id": reserved["_id"]},
        {"$set": {"leaseUntil": datetime.now(timezone.utc) - timedelta(seconds=1)}},
    )
    recovered = await process(database, owner_id, event)
    assert recovered["status"] == "duplicate"
    assert recovered["ledger"]["progressionRevision"] == 1
    assert recovered["ledger"]["coins"] == {"confirmed": 60}
    stored = await database.ledgers.find_one({"_id": ledger["_id"]})
    assert stored["appliedEventIds"] == {"1": event.eventId}

