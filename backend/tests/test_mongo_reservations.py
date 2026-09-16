"""Mock-level adapter tests; real MongoDB tests live in integration suite."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from pymongo.errors import DuplicateKeyError

from progression.mongo_reservations import (
    MongoReservationStore, ProgressionConflict, ReservationBusy,
    ReservationInvariantError,
)


@pytest.fixture
def store():
    events, ledgers = AsyncMock(), AsyncMock()
    client = MagicMock()
    session = MagicMock()
    client.start_session = AsyncMock(return_value=session)
    events.database.client = client
    return MongoReservationStore(events, ledgers)


def checkpoint():
    return {"bookId": "book1", "currentSceneId": "start", "terminal": False}


def projection():
    return {"coins": {"confirmed": 260}, "achievements": {}, "derived": {},
            "checkpoint": {"bookId": "book1", "currentSceneId": "next", "terminal": False}}


@pytest.mark.asyncio
async def test_indexes_include_durable_unique_revision_reservation(store):
    await store.ensure_indexes()
    assert store.events.create_index.await_count == 2
    args, kwargs = store.events.create_index.await_args_list[1]
    assert args[0] == [("ledgerId", 1), ("targetRevision", 1)]
    assert kwargs["unique"] is True
    assert kwargs["partialFilterExpression"] == {"targetRevision": {"$exists": True}}


@pytest.mark.asyncio
async def test_competing_reservation_cannot_remove_winner(store):
    store.events.find_one.return_value = {"_id": "loser", "ledgerId": "l", "eventId": "b",
                                          "payloadHash": "h", "status": "received"}
    store.ledgers.find_one.return_value = {"progressionRevision": 0}
    store.events.find_one_and_update.side_effect = DuplicateKeyError("target taken")
    with pytest.raises(ProgressionConflict):
        await store.reserve(ledger_id="l", event_id="b", payload_hash="h",
                            base_revision=0, awards={})
    store.events.delete_one.assert_not_awaited()
    store.events.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_reservation_rejected_before_target_claim(store):
    store.events.find_one.return_value = {"_id": "e", "ledgerId": "l", "eventId": "e",
                                          "payloadHash": "h", "status": "received"}
    store.ledgers.find_one.return_value = {"progressionRevision": 1}
    with pytest.raises(ProgressionConflict, match="revision changed"):
        await store.reserve(ledger_id="l", event_id="e", payload_hash="h",
                            base_revision=0, awards={})
    store.events.find_one_and_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_reused_event_id_with_changed_payload_is_rejected(store):
    store.events.insert_one.side_effect = DuplicateKeyError("event exists")
    store.events.find_one.return_value = {"_id": "e", "payloadHash": "original", "status": "applied"}
    with pytest.raises(ReservationInvariantError, match="payload_mismatch"):
        await store.reserve(ledger_id="l", event_id="e", payload_hash="changed",
                            base_revision=0, awards={})
    store.events.find_one_and_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_lease_takeover_requires_expiry(store):
    store.events.find_one_and_update.return_value = None
    with pytest.raises(ReservationBusy):
        await store.acquire({"_id": "e", "status": "committing"})
    filt = store.events.find_one_and_update.await_args.args[0]
    assert filt["leaseUntil"]["$lte"].tzinfo is not None


@pytest.mark.asyncio
async def test_commit_uses_persisted_projection_in_single_conditional_write(store):
    event = {"_id": "e", "ledgerId": "l", "status": "committing", "leaseOwner": "worker",
             "baseRevision": 4, "targetRevision": 5, "nextProjection": projection(),
             "expectedCheckpoint": checkpoint()}
    store.events.find_one.return_value = event
    store.events.find_one_and_update.return_value = {**event, "commitFence": 1}
    store.ledgers.find_one_and_update.return_value = {"progressionRevision": 5}
    result = await store.commit(event=event, lease_owner="worker")
    assert result["progressionRevision"] == 5
    fence_filter, fence_update = store.events.find_one_and_update.await_args.args
    assert fence_filter["leaseOwner"] == "worker"
    assert fence_update == {"$inc": {"commitFence": 1}}
    fence_session = store.events.find_one_and_update.await_args.kwargs["session"]
    filt, update = store.ledgers.find_one_and_update.await_args.args
    assert store.ledgers.find_one_and_update.await_args.kwargs["session"] is fence_session
    assert filt["progressionRevision"] == 4
    assert filt["checkpoint.currentSceneId"] == "start"
    assert update["$set"]["progressionRevision"] == 5
    assert update["$set"]["coins"]["confirmed"] == 260


@pytest.mark.asyncio
async def test_unpersisted_projection_cannot_commit(store):
    event = {"_id": "e", "ledgerId": "l", "status": "committing", "leaseOwner": "worker",
             "baseRevision": 0, "targetRevision": 1}
    store.events.find_one.return_value = event
    with pytest.raises(ReservationInvariantError, match="no durable projection"):
        await store.commit(event=event, lease_owner="worker", next_projection=projection(),
                           expected_checkpoint=checkpoint())
    store.events.find_one_and_update.assert_not_awaited()
    store.ledgers.find_one_and_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_crash_after_commit_can_finalise_even_sixty_revisions_later(store):
    event = {"_id": "e", "ledgerId": "l", "eventId": "a", "payloadHash": "h",
             "status": "committing", "baseRevision": 4, "targetRevision": 5}
    store.ledgers.find_one.return_value = {"progressionRevision": 65}
    store.events.find_one_and_update.return_value = {**event, "status": "applied", "resultRevision": 5}
    result = await store.finalise(event=event, payload_hash="h")
    assert result["resultRevision"] == 5
    store.ledgers.find_one_and_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_uncommitted_event_cannot_be_finalised(store):
    event = {"_id": "e", "ledgerId": "l", "eventId": "a", "payloadHash": "h",
             "status": "committing", "baseRevision": 4, "targetRevision": 5}
    store.ledgers.find_one.return_value = {"progressionRevision": 4}
    with pytest.raises(ReservationInvariantError, match="cannot finalise"):
        await store.finalise(event=event, payload_hash="h")
    store.events.find_one_and_update.assert_not_awaited()
