"""Disposable MongoDB regression: a changed content pin must fence commit."""
import os
from uuid import uuid4

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from progression.mongo_reservations import MongoReservationStore, ProgressionConflict


@pytest.mark.asyncio
async def test_commit_rejects_changed_content_pin_without_advancing_rewards():
    uri = os.environ.get("TEST_MONGO_URI")
    if not uri:
        pytest.skip("TEST_MONGO_URI not set: disposable MongoDB required")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    database = client[f"phase6b_pin_fence_{uuid4().hex}"]
    store = MongoReservationStore(database.ledgers, database.progression_events)
    ledger_id = uuid4().hex
    checkpoint = {"bookId": "book1", "contentVersion": 1,
                  "currentSceneId": "start", "terminal": False}
    try:
        await client.admin.command("ping")
        await store.ensure_indexes()
        await store.ledgers.insert_one({
            "_id": ledger_id, "ownerType": "account", "ownerId": uuid4().hex,
            "progressionRevision": 0, "checkpoint": checkpoint,
            "coins": {"confirmed": 0}, "achievements": {}, "derived": {},
        })
        event = await store.reserve(
            ledger_id=ledger_id, event_id="pin-fence", payload_hash="digest",
            base_revision=0, awards={}, expected_checkpoint=checkpoint,
            next_projection={"coins": {"confirmed": 0}, "achievements": {},
                             "derived": {}, "checkpoint": {**checkpoint, "currentSceneId": "next"}},
        )
        # Simulate an unauthorized concurrent pin change at the same revision.
        await store.ledgers.update_one({"_id": ledger_id},
                                       {"$set": {"checkpoint.contentVersion": 2}})
        with pytest.raises(ProgressionConflict):
            await store.commit(event=event, lease_owner=event["leaseOwner"])
        ledger = await store.ledgers.find_one({"_id": ledger_id})
        assert ledger["progressionRevision"] == 0
        assert ledger["checkpoint"]["contentVersion"] == 2
        assert ledger["coins"]["confirmed"] == 0
        assert (await store.events.find_one({"_id": event["_id"]}))["status"] == "committing"
    finally:
        await client.drop_database(database.name)
        client.close()
