"""Disposable replica-set probe for the transaction fencing design.

This verifies MongoDB's same-document write conflict; it does not exercise
MongoReservationStore.commit() and is NOT proof that the adapter is fenced.
"""
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure


@pytest.mark.asyncio
async def test_transactional_event_write_conflicts_with_concurrent_takeover():
    uri = os.environ.get("TEST_MONGO_URI")
    if not uri:
        pytest.skip("TEST_MONGO_URI not set: disposable replica set required")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    database = client[f"phase6b_fence_probe_{uuid4().hex}"]
    owner = uuid4().hex
    try:
        await client.admin.command("ping")
        event_id = uuid4().hex
        await database.events.insert_one({
            "_id": event_id, "status": "committing", "leaseOwner": owner,
            "leaseUntil": datetime.now(timezone.utc) + timedelta(minutes=5),
        })
        async with await client.start_session() as session:
            async with session.start_transaction():
                fenced = await database.events.find_one_and_update(
                    {"_id": event_id, "status": "committing", "leaseOwner": owner,
                     "leaseUntil": {"$gt": datetime.now(timezone.utc)}},
                    {"$inc": {"commitFence": 1}}, session=session,
                )
                assert fenced is not None
                # Simulate an ownership-changing write while the transaction
                # holds its event-document write. MongoDB must reject it.
                with pytest.raises(OperationFailure) as conflict:
                    await database.events.update_one(
                        {"_id": event_id, "status": "committing"},
                        {"$set": {"leaseOwner": uuid4().hex}},
                    )
                assert conflict.value.has_error_label("TransientTransactionError") or conflict.value.code == 112
        persisted = await database.events.find_one({"_id": event_id})
        assert persisted["leaseOwner"] == owner
        assert persisted["commitFence"] == 1
    finally:
        await client.drop_database(database.name)
        client.close()
