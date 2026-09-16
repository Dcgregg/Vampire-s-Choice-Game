"""Deterministic proof-mutation race against disposable MongoDB only."""
import os
from uuid import uuid4

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from progression.attributed_finalisation import finalise_attributed_event
from progression.attribution import AttributionUnproven


class MutateBeforeFence:
    """Inject an independent writer after the transactional read, before its fence."""

    def __init__(self, collection, ledger_id):
        self.collection = collection
        self.ledger_id = ledger_id
        self.mutated = False

    async def find_one(self, *args, **kwargs):
        return await self.collection.find_one(*args, **kwargs)

    async def update_one(self, *args, **kwargs):
        if not self.mutated:
            self.mutated = True
            await self.collection.update_one(
                {"_id": self.ledger_id},
                {"$set": {"appliedEventIds.1": "foreign"}},
            )
        return await self.collection.update_one(*args, **kwargs)


@pytest.mark.asyncio
async def test_marker_mutation_after_read_cannot_finalise_event():
    uri = os.environ.get("TEST_MONGO_URI")
    if not uri:
        pytest.skip("TEST_MONGO_URI required; never use production MongoDB")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    db = client[f"p6b_final_race_{uuid4().hex}"]
    try:
        await client.admin.command("ping")
        ledger_id = uuid4().hex
        event = {"_id": uuid4().hex, "ledgerId": ledger_id, "eventId": "own",
                 "payloadHash": "digest", "baseRevision": 0,
                 "targetRevision": 1, "status": "committing"}
        await db.ledgers.insert_one({
            "_id": ledger_id, "progressionRevision": 1,
            "appliedEventIds": {"1": "own"},
        })
        await db.events.insert_one(dict(event))
        intercepted = MutateBeforeFence(db.ledgers, ledger_id)
        with pytest.raises(AttributionUnproven):
            await finalise_attributed_event(
                intercepted, db.events, event=event, payload_hash="digest",
            )
        assert intercepted.mutated
        ledger = await db.ledgers.find_one({"_id": ledger_id})
        stored = await db.events.find_one({"_id": event["_id"]})
        assert ledger["appliedEventIds"]["1"] == "foreign"
        assert stored["status"] == "committing"
        assert "resultRevision" not in stored
    finally:
        await client.drop_database(db.name)
        client.close()
