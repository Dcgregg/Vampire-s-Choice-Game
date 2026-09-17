"""Inert end-to-end choice-plan tests against disposable MongoDB only.

No HTTP route, production credentials or real player data. This tests the
existing reservation adapter with a plan derived from a server-loaded ledger.
"""
import os
from uuid import uuid4

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from progression.attributed_mongo_reservations import AttributedMongoReservationStore
from progression.mongo_reservations import ProgressionConflict, ReservationInvariantError
from progression.trusted_choice_reservation import plan_account_choice_reservation
from test_choice_checkpoint_guard import event, registry


@pytest.mark.asyncio
async def test_server_planned_choice_commits_once_and_replay_cannot_award_again():
    uri = os.environ.get('TEST_MONGO_URI')
    if not uri:
        pytest.skip('TEST_MONGO_URI required; never connect to production MongoDB')
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    db = client['p6b_choice_plan_' + uuid4().hex]
    try:
        await client.admin.command('ping')
        store = AttributedMongoReservationStore(db.ledgers, db.events)
        await store.ensure_indexes()
        owner = 'account-' + uuid4().hex
        ledger_id = uuid4().hex
        checkpoint = {'bookId': 'book1', 'contentVersion': 1,
                      'currentSceneId': 'start', 'terminal': False}
        await db.ledgers.insert_one({
            '_id': ledger_id, 'ownerType': 'account', 'ownerId': owner,
            'progressionRevision': 3, 'appliedEventIds': {
                '3': '550e8400-e29b-41d4-a716-446655440001'},
            'checkpoint': checkpoint, 'coins': {'confirmed': 20},
            'achievements': {}, 'derived': {
                'coins': 20, 'affinity': {'friend': 0},
                'flags': {}, 'achievements': []},
        })
        current = await db.ledgers.find_one({'_id': ledger_id})
        choice = event()
        args = plan_account_choice_reservation(
            registry(), current, choice, authenticated_user_id=owner)
        reserved = await store.reserve(**args)
        assert reserved['status'] == 'committing'
        committed = await store.commit(event=reserved, lease_owner=reserved['leaseOwner'])
        assert committed['progressionRevision'] == 4
        assert committed['appliedEventIds']['4'] == choice.eventId
        assert committed['coins']['confirmed'] == 30
        applied = await store.finalise(event=reserved, payload_hash=args['payload_hash'])
        assert applied['status'] == 'applied'
        assert (await store.finalise(event=applied, payload_hash=args['payload_hash']))['status'] == 'applied'
        after = await db.ledgers.find_one({'_id': ledger_id})
        assert after['coins']['confirmed'] == 30
        assert after['progressionRevision'] == 4
        with pytest.raises((ProgressionConflict, ReservationInvariantError)):
            await store.reserve(**args)
        assert (await db.ledgers.find_one({'_id': ledger_id}))['coins']['confirmed'] == 30
    finally:
        await client.drop_database(db.name)
        client.close()
