"""Inert competing-choice regression against disposable MongoDB only."""
import asyncio
import os
from uuid import uuid4

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from progression.attributed_mongo_reservations import AttributedMongoReservationStore
from progression.mongo_reservations import ProgressionConflict
from progression.trusted_choice_reservation import plan_account_choice_reservation
from test_choice_checkpoint_guard import event, registry


@pytest.mark.asyncio
async def test_competing_choices_cannot_both_reserve_the_same_revision():
    uri = os.environ.get('TEST_MONGO_URI')
    if not uri:
        pytest.skip('TEST_MONGO_URI required; never connect to production MongoDB')
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    db = client['p6b_competing_choices_' + uuid4().hex]
    try:
        await client.admin.command('ping')
        store = AttributedMongoReservationStore(db.ledgers, db.events)
        await store.ensure_indexes()
        owner, ledger_id = 'account-' + uuid4().hex, uuid4().hex
        checkpoint = {'bookId': 'book1', 'contentVersion': 1,
                      'currentSceneId': 'start', 'terminal': False}
        await db.ledgers.insert_one({
            '_id': ledger_id, 'ownerType': 'account', 'ownerId': owner,
            'progressionRevision': 3,
            'appliedEventIds': {'3': '550e8400-e29b-41d4-a716-446655440001'},
            'checkpoint': checkpoint, 'coins': {'confirmed': 20},
            'achievements': {}, 'derived': {
                'coins': 20, 'affinity': {'friend': 0},
                'flags': {}, 'achievements': []},
        })
        current = await db.ledgers.find_one({'_id': ledger_id})
        choices = [event(eventId=str(uuid4())),
                   event(eventId=str(uuid4()), choiceId='spend_and_change')]
        plans = [plan_account_choice_reservation(
            registry(), current, choice, authenticated_user_id=owner,
        ) for choice in choices]
        results = await asyncio.gather(
            *(store.reserve(**plan) for plan in plans), return_exceptions=True,
        )
        winners = [result for result in results if isinstance(result, dict)]
        losers = [result for result in results if isinstance(result, BaseException)]
        assert len(winners) == 1
        assert len(losers) == 1 and isinstance(losers[0], ProgressionConflict)
        winner = winners[0]
        committed = await store.commit(event=winner, lease_owner=winner['leaseOwner'])
        applied = await store.finalise(event=winner, payload_hash=winner['payloadHash'])
        assert applied['status'] == 'applied'
        assert committed['progressionRevision'] == 4
        assert committed['appliedEventIds']['4'] == winner['eventId']
        assert committed['coins']['confirmed'] in (0, 30)
        assert await db.events.count_documents({
            'ledgerId': ledger_id, 'targetRevision': 4,
        }) == 1
        assert (await db.ledgers.find_one({'_id': ledger_id}))['progressionRevision'] == 4
    finally:
        await client.drop_database(db.name)
        client.close()
