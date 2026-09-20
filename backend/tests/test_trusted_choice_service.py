"""Pure orchestration tests for authenticated trusted-choice processing."""
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from progression.canonical_event import canonical_event_sha256
from progression.strict_event_input import StrictChoiceEvent
from progression.trusted_choice_service import (
    TrustedChoiceConflict, TrustedChoiceIndeterminate, TrustedChoiceUnavailable,
    process_account_choice, public_account_ledger,
)
from test_choice_checkpoint_guard import event, registry


def ledger():
    return {
        "_id": "ledger-a", "ownerType": "account", "ownerId": "account-a",
        "progressionRevision": 3,
        "appliedEventIds": {"3": "550e8400-e29b-41d4-a716-446655440001"},
        "checkpoint": {"bookId": "book1", "contentVersion": 1,
                       "currentSceneId": "start", "terminal": False},
        "coins": {"confirmed": 20}, "achievements": {},
        "derived": {"coins": 20, "affinity": {"friend": 0},
                    "flags": {}, "achievements": []},
    }


class Ledgers:
    def __init__(self, current=None):
        self.current = deepcopy(current)
        self.queries = []

    async def find_one(self, query):
        self.queries.append(query)
        if self.current is None:
            return None
        if any(self.current.get(key) != value for key, value in query.items()):
            return None
        return deepcopy(self.current)


class Events:
    def __init__(self, existing=None):
        self.existing = deepcopy(existing)

    async def find_one(self, _query):
        return deepcopy(self.existing)


def applied(choice: StrictChoiceEvent):
    return {
        "_id": "event-doc", "ledgerId": "ledger-a", "eventId": choice.eventId,
        "payloadHash": canonical_event_sha256(choice.model_dump(mode="python")),
        "expectedOwnerType": "account", "expectedOwnerId": "account-a",
        "status": "applied", "baseRevision": 3, "targetRevision": 4,
    }


@pytest.mark.asyncio
async def test_missing_account_ledger_fails_without_event_lookup():
    ledgers, events = Ledgers(), Events()
    with pytest.raises(TrustedChoiceUnavailable):
        await process_account_choice(
            ledgers, events, registry(), authenticated_user_id="account-a",
            event=event(),
        )
    assert ledgers.queries == [{"ownerType": "account", "ownerId": "account-a"}]


@pytest.mark.asyncio
async def test_applied_duplicate_returns_authoritative_public_ledger():
    choice = event()
    current = ledger()
    current["progressionRevision"] = 4
    current["appliedEventIds"]["4"] = choice.eventId
    result = await process_account_choice(
        Ledgers(current), Events(applied(choice)), registry(),
        authenticated_user_id="account-a", event=choice,
    )
    assert result["status"] == "duplicate"
    assert result["ledger"]["progressionRevision"] == 4
    assert result["ledger"]["coins"] == {"confirmed": 20}
    assert "_id" not in result["ledger"] and "ownerId" not in result["ledger"]


@pytest.mark.asyncio
async def test_reused_event_id_with_changed_payload_conflicts():
    choice = event()
    existing = applied(choice)
    existing["payloadHash"] = "different"
    with pytest.raises(TrustedChoiceConflict, match="different intent"):
        await process_account_choice(
            Ledgers(ledger()), Events(existing), registry(),
            authenticated_user_id="account-a", event=choice,
        )


@pytest.mark.asyncio
async def test_new_choice_uses_server_plan_and_returns_reloaded_ledger(monkeypatch):
    ledgers = Ledgers(ledger())
    events = Events()
    choice = event()
    reserved = {"_id": "event-doc", "ledgerId": "ledger-a",
                "eventId": choice.eventId, "payloadHash": "digest",
                "status": "committing", "baseRevision": 3, "targetRevision": 4,
                "leaseOwner": "worker", "expectedOwnerType": "account",
                "expectedOwnerId": "account-a"}
    store = type("Store", (), {})()
    store.reserve = AsyncMock(return_value=reserved)

    async def commit(**_kwargs):
        ledgers.current["progressionRevision"] = 4
        ledgers.current["coins"]["confirmed"] = 30
        ledgers.current["checkpoint"]["currentSceneId"] = "next"
        ledgers.current["appliedEventIds"]["4"] = choice.eventId
        return deepcopy(ledgers.current)

    store.commit = AsyncMock(side_effect=commit)
    store.finalise = AsyncMock(return_value={**reserved, "status": "applied"})
    monkeypatch.setattr(
        "progression.trusted_choice_service.AttributedMongoReservationStore",
        lambda *_args: store,
    )
    result = await process_account_choice(
        ledgers, events, registry(), authenticated_user_id="account-a",
        event=choice,
    )
    assert result["status"] == "confirmed"
    assert result["ledger"]["coins"] == {"confirmed": 30}
    assert store.reserve.await_args.kwargs["expected_owner_id"] == "account-a"
    store.commit.assert_awaited_once()
    store.finalise.assert_awaited_once()


@pytest.mark.parametrize("changes", [
    {"coins": {"confirmed": True}}, {"coins": {"confirmed": -1}},
    {"achievements": []}, {"progressionRevision": True},
    {"checkpoint": {"bookId": "book1", "contentVersion": 1,
                    "currentSceneId": "start", "terminal": "no"}},
])
def test_public_ledger_fails_closed_on_malformed_authority(changes):
    current = ledger()
    current.update(changes)
    with pytest.raises(TrustedChoiceIndeterminate, match="malformed"):
        public_account_ledger(current)
