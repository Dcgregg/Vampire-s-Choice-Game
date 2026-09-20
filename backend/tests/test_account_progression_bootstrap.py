"""Pure account bootstrap tests; no live player data or production services."""
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from progression import account_progression_bootstrap as service
from progression.account_progression_bootstrap import (
    AccountProgressionUnavailable, bootstrap_account_progression,
)


REGISTRY = {"characters": {"friend": 0}, "books": {"book1": {"version": 1,
            "scenes": {"start": {"choices": {}}}}}}


def granted(**changes):
    doc = {
        "_id": "ledger-a", "ownerType": "account", "ownerId": "account-a",
        "progressionRevision": 0, "coins": {"confirmed": 50},
        "achievements": {}, "derived": {"coins": 50, "affinity": {"friend": 0},
                                         "flags": {}, "achievements": []},
        "checkpoint": {"bookId": "book1", "contentVersion": 1,
                       "currentSceneId": "start", "terminal": False},
        "openingGranted": True, "lifecycleApplied": [], "appliedEventIds": {},
    }
    doc.update(changes)
    return doc


@pytest.mark.asyncio
async def test_authenticated_account_receives_public_50_coin_ledger(monkeypatch):
    initializer = AsyncMock(return_value=granted())
    monkeypatch.setattr(service, "initialize_granted_account_ledger", initializer)
    result = await bootstrap_account_progression(
        object(), REGISTRY, authenticated_user_id="account-a",
        book_id="book1", content_version=1, scene_id="start",
    )
    assert result["coins"] == {"confirmed": 50}
    assert result["achievements"] == {}
    assert "_id" not in result and "ownerId" not in result
    assert initializer.await_args.kwargs["owner_id"] == "account-a"


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"openingGranted": False}, {"openingGranted": None},
    {"coins": {"confirmed": 0}}, {"coins": {"confirmed": 250}},
])
async def test_fresh_unawarded_or_wrong_value_ledger_fails_closed(monkeypatch, changes):
    initializer = AsyncMock(return_value=granted(**deepcopy(changes)))
    monkeypatch.setattr(service, "initialize_granted_account_ledger", initializer)
    with pytest.raises(AccountProgressionUnavailable):
        await bootstrap_account_progression(
            object(), REGISTRY, authenticated_user_id="account-a",
            book_id="book1", content_version=1, scene_id="start",
        )


@pytest.mark.asyncio
async def test_progressed_granted_ledger_is_returned_without_top_up(monkeypatch):
    existing = granted(progressionRevision=7, coins={"confirmed": 13},
                       appliedEventIds={"7": "event-seven"})
    initializer = AsyncMock(return_value=existing)
    monkeypatch.setattr(service, "initialize_granted_account_ledger", initializer)
    result = await bootstrap_account_progression(
        object(), REGISTRY, authenticated_user_id="account-a",
        book_id="book1", content_version=1, scene_id="start",
    )
    assert result["progressionRevision"] == 7
    assert result["coins"] == {"confirmed": 13}
