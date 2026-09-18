"""Disposable-MongoDB recovery sweep checks using the attribution-aware adapter.

Never run with production credentials. The sweep is inert and no scheduler is wired.
"""
from datetime import datetime, timedelta, timezone

import pytest

from progression.attribution import AttributionUnproven
from progression.recovery_sweep import sweep_expired
from test_attributed_mongo_reservations_integration import reserved, store


async def expire(store, event):
    await store.events.update_one(
        {"_id": event["_id"]},
        {"$set": {"leaseUntil": datetime.now(timezone.utc) - timedelta(seconds=5)}},
    )


@pytest.mark.asyncio
async def test_attributed_sweep_recovers_expired_event_once(store):
    event = await reserved(store)
    await expire(store, event)

    first = await sweep_expired(store)
    second = await sweep_expired(store)

    assert first.examined == first.applied == 1
    assert second.examined == 0
    ledger = await store.ledgers.find_one({"_id": event["ledgerId"]})
    assert ledger["progressionRevision"] == 1
    assert ledger["appliedEventIds"] == {"1": event["eventId"]}
    assert ledger["coins"]["confirmed"] == 10
    assert (await store.events.find_one({"_id": event["_id"]}))["status"] == "applied"


@pytest.mark.asyncio
@pytest.mark.parametrize("foreign_revision", [1, 4])
async def test_attributed_sweep_does_not_finalise_foreign_revision(store, foreign_revision):
    event = await reserved(store)
    await expire(store, event)
    await store.ledgers.update_one(
        {"_id": event["ledgerId"]},
        {"$set": {"progressionRevision": foreign_revision,
                  "appliedEventIds.1": "foreign-event"}},
    )

    with pytest.raises(AttributionUnproven):
        await sweep_expired(store)

    ledger = await store.ledgers.find_one({"_id": event["ledgerId"]})
    assert ledger["progressionRevision"] == foreign_revision
    assert ledger["appliedEventIds"] == {"1": "foreign-event"}
    assert ledger["coins"]["confirmed"] == 0
    assert (await store.events.find_one({"_id": event["_id"]}))["status"] == "committing"
