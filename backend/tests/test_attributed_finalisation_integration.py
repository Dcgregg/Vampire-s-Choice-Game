"""Disposable MongoDB tests for the inert attributed finalisation candidate."""
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from progression.attributed_finalisation import finalise_attributed_event
from progression.attribution import AttributionUnproven


@pytest_asyncio.fixture
async def collections():
    uri = os.environ.get("TEST_MONGO_URI")
    if not uri:
        pytest.skip("TEST_MONGO_URI required; never run against production")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    db = client[f"phase6b_finalisation_{uuid4().hex}"]
    try:
        await client.admin.command("ping")
        yield db.ledgers, db.events
    finally:
        await client.drop_database(db.name)
        client.close()


async def seed(ledgers, events, *, revision=1, marker="own"):
    ledger_id = uuid4().hex
    event = {"_id": uuid4().hex, "ledgerId": ledger_id, "eventId": "own",
             "payloadHash": "digest", "baseRevision": 0, "targetRevision": 1,
             "status": "committing"}
    await ledgers.insert_one({"_id": ledger_id, "progressionRevision": revision,
                              "appliedEventIds": {"1": marker}})
    await events.insert_one(dict(event))
    return event


@pytest.mark.asyncio
async def test_matching_marker_finalises_and_retries_without_second_write(collections):
    ledgers, events = collections
    event = await seed(ledgers, events)
    first = await finalise_attributed_event(ledgers, events, event=event, payload_hash="digest")
    second = await finalise_attributed_event(ledgers, events, event=event, payload_hash="digest")
    assert first["status"] == second["status"] == "applied"
    assert first["resultRevision"] == second["resultRevision"] == 1
    assert first["appliedAt"] == second["appliedAt"]
    assert (await ledgers.find_one({"_id": event["ledgerId"]}))["progressionRevision"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("revision,marker", [(1, "foreign"), (4, "foreign"), (0, "own"), (4, None)])
async def test_foreign_missing_or_uncommitted_marker_cannot_finalise(collections, revision, marker):
    ledgers, events = collections
    event = await seed(ledgers, events, revision=revision, marker=marker)
    with pytest.raises(AttributionUnproven):
        await finalise_attributed_event(ledgers, events, event=event, payload_hash="digest")
    assert (await events.find_one({"_id": event["_id"]}))["status"] == "committing"


@pytest.mark.asyncio
async def test_matching_marker_survives_later_revisions(collections):
    ledgers, events = collections
    event = await seed(ledgers, events, revision=4)
    result = await finalise_attributed_event(ledgers, events, event=event, payload_hash="digest")
    assert result["status"] == "applied"


@pytest.mark.asyncio
async def test_tampered_event_or_payload_fails_closed(collections):
    ledgers, events = collections
    event = await seed(ledgers, events)
    with pytest.raises(AttributionUnproven):
        await finalise_attributed_event(ledgers, events, event={**event, "eventId": "foreign"}, payload_hash="digest")
    with pytest.raises(AttributionUnproven):
        await finalise_attributed_event(ledgers, events, event=event, payload_hash="different")
    assert (await events.find_one({"_id": event["_id"]}))["status"] == "committing"


@pytest.mark.asyncio
@pytest.mark.parametrize("result_revision", [None, 0, 2, True])
async def test_applied_retry_rejects_missing_or_inconsistent_result_revision(collections, result_revision):
    ledgers, events = collections
    event = await seed(ledgers, events)
    fields = {"status": "applied"}
    if result_revision is not None:
        fields["resultRevision"] = result_revision
    await events.update_one({"_id": event["_id"]}, {"$set": fields})
    with pytest.raises(AttributionUnproven, match="result revision"):
        await finalise_attributed_event(ledgers, events, event=event, payload_hash="digest")
    stored = await events.find_one({"_id": event["_id"]})
    assert stored["status"] == "applied"
    assert stored.get("resultRevision") == result_revision
