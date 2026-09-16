"""Disposable replica-set probe for the transaction fencing design.

This tests a stale transaction against a completed event ownership change.
It does not exercise MongoReservationStore.commit() or prove the adapter is fenced.
"""
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure


@pytest.mark.asyncio
async def test_stale_transaction_cannot_fence_event_after_takeover():
    uri = os.environ.get("TEST_MONGO_URI")
    if not uri:
        pytest.skip("TEST_MONGO_URI not set: disposable replica set required")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    database = client[f"phase6b_fence_probe_{uuid4().hex}"]
    owner, successor = uuid4().hex, uuid4().hex
    try:
        await client.admin.command("ping")
        event_id = uuid4().hex
        await database.events.insert_one({
            "_id": event_id, "status": "committing", "leaseOwner": owner,
            "leaseUntil": datetime.now(timezone.utc) + timedelta(minutes=5),
        })
        async with await client.start_session() as session:
            async with session.start_transaction():
                # Establish a snapshot before a different client takes ownership.
                snapshot = await database.events.find_one({"_id": event_id}, session=session)
                assert snapshot["leaseOwner"] == owner
                takeover = await database.events.update_one(
                    {"_id": event_id, "leaseOwner": owner},
                    {"$set": {"leaseOwner": successor}},
                )
                assert takeover.modified_count == 1
                # The stale transaction must not successfully write the event.
                # MongoDB may signal a write conflict rather than return no match.
                try:
                    fenced = await database.events.find_one_and_update(
                        {"_id": event_id, "status": "committing", "leaseOwner": owner,
                         "leaseUntil": {"$gt": datetime.now(timezone.utc)}},
                        {"$inc": {"commitFence": 1}}, session=session,
                    )
                except OperationFailure as exc:
                    assert exc.has_error_label("TransientTransactionError") or exc.code == 112
                    await session.abort_transaction()
                else:
                    assert fenced is None, "stale owner fenced the event after takeover"
        persisted = await database.events.find_one({"_id": event_id})
        assert persisted["leaseOwner"] == successor
        assert "commitFence" not in persisted
    finally:
        await client.drop_database(database.name)
        client.close()
