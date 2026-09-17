"""Disposable Mongo regression: a foreign account cannot create a choice reservation.

This is a planner boundary test, not a substitute for verified HTTP sessions.
"""
import os
from uuid import uuid4

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from progression.attributed_mongo_reservations import AttributedMongoReservationStore
from progression.trusted_choice_reservation import plan_account_choice_reservation
from progression.trusted_owner import ProgressionAccessDenied
from test_choice_checkpoint_guard import event, registry


@pytest.mark.asyncio
async def test_foreign_owner_cannot_create_reservation_or_change_ledger():
    uri = os.environ.get('TEST_MONGO_URI')
    if not uri:
        pytest.skip('TEST_MONGO_URI required; never connect to production MongoDB')
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    db = client['p6b_foreign_choice_' + uuid4().hex]
    try:
        await client.admin.command('ping')
        store = AttributedMongoReservationStore(db.ledgers, db.events)
        await store.ensure_indexes()
        owner, foreign = 'account-' + uuid4().hex, 'account-' + uuid4().hex
        ledger_id = uuid4().hex
        await db.ledgers.insert_one({
            '_id': ledger_id, 'ownerType': 'account', 'ownerId': owner,
            'progressionRevision': 3,
            'appliedEventIds': {'3': '550e8400-e29b-41d4-a716-446655440001'},
            'checkpoint': {'bookId': 'book1', 'contentVersion': 1,
                           'currentSceneId': 'start', 'terminal': False},
            'coins': {'confirmed': 20}, 'achievements': {},
            'derived': {'coins': 20, 'affinity': {'friend': 0},
                        'flags': {}, 'achievements': []},
        })
        loaded = await db.ledgers.find_one({'_id': ledger_id})
        with pytest.raises(ProgressionAccessDenied):
            args = plan_account_choice_reservation(
                registry(), loaded, event(), authenticated_user_id=foreign)
            await store.reserve(**args)
        assert await db.events.count_documents({'ledgerId': ledger_id}) == 0
        after = await db.ledgers.find_one({'_id': ledger_id})
        assert after == loaded
    finally:
        await client.drop_database(db.name)
        client.close()
