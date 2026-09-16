"""Real disposable MongoDB coverage for the inert Phase 6B recovery sweep."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from progression.mongo_reservations import MongoReservationStore
from progression.recovery_sweep import sweep_expired
from test_mongo_reservations_integration import mongo_store, projection, seeded


async def reserve(store, ledger_id, checkpoint, event_id, *, complete=True):
    return await store.reserve(
        ledger_id=ledger_id, event_id=event_id, payload_hash=event_id,
        base_revision=0, awards={"coins": 10},
        next_projection=projection() if complete else None,
        expected_checkpoint=checkpoint if complete else None,
    )


async def expire(store, event):
    await store.events.update_one(
        {"_id": event["_id"]},
        {"$set": {"leaseUntil": datetime.now(timezone.utc) - timedelta(seconds=5)}},
    )


@pytest.mark.asyncio
async def test_sweep_recovers_only_expired_events_and_obeys_limit(mongo_store):
    store = mongo_store
    ids = []
    for name in ("first", "second", "active"):
        ledger_id, checkpoint = await seeded(store)
        event = await reserve(store, ledger_id, checkpoint, name)
        ids.append((ledger_id, event))
        if name != "active":
            await expire(store, event)
    first = await sweep_expired(store, limit=1)
    assert first.examined == first.applied == 1
    second = await sweep_expired(store, limit=10)
    assert second.examined == second.applied == 1
    assert (await sweep_expired(store)).examined == 0
    revisions = [(await store.ledgers.find_one({"_id": ledger_id}))["progressionRevision"]
                 for ledger_id, _ in ids]
    assert revisions == [1, 1, 0]


@pytest.mark.asyncio
async def test_two_sweep_workers_cannot_double_apply(mongo_store):
    store = mongo_store
    ledger_id, checkpoint = await seeded(store)
    event = await reserve(store, ledger_id, checkpoint, "race")
    await expire(store, event)
    results = await asyncio.gather(sweep_expired(store), sweep_expired(store))
    assert sum(result.applied for result in results) == 1
    assert sum(result.invalid + result.conflicted for result in results) == 0
    ledger = await store.ledgers.find_one({"_id": ledger_id})
    assert ledger["progressionRevision"] == 1
    assert ledger["coins"]["confirmed"] == 260
    assert await store.events.count_documents({"ledgerId": ledger_id, "status": "applied"}) == 1


@pytest.mark.asyncio
async def test_sweep_fails_closed_on_legacy_reservation_without_projection(mongo_store):
    store = mongo_store
    ledger_id, checkpoint = await seeded(store)
    event = await reserve(store, ledger_id, checkpoint, "legacy", complete=False)
    await expire(store, event)
    result = await sweep_expired(store)
    assert result.examined == result.invalid == 1
    assert result.applied == 0
    assert (await store.ledgers.find_one({"_id": ledger_id}))["progressionRevision"] == 0
    assert (await store.events.find_one({"_id": event["_id"]}))["status"] == "committing"


@pytest.mark.asyncio
async def test_sweep_rejects_invalid_batch_size(mongo_store):
    for limit in (0, -1, True, 1001, 1.5):
        with pytest.raises(ValueError):
            await sweep_expired(mongo_store, limit=limit)
