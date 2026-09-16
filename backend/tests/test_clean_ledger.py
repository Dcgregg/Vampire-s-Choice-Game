"""Pure clean-seed tests: no database, accounts or live saves."""
from copy import deepcopy

import pytest

from progression.clean_ledger import InvalidCleanLedger, validate_clean_ledger
from progression.reducer import new_state


def registry():
    return {"characters": {"friend": 0}, "books": {"book1": {
        "version": 1, "scenes": {"start": {"choices": {}}}}}}


def seed():
    content = registry()
    return {"ownerType": "account", "ownerId": "trusted-account",
            "progressionRevision": 0, "coins": {"confirmed": 0},
            "achievements": {}, "derived": new_state(content),
            "checkpoint": {"bookId": "book1", "contentVersion": 1,
                           "currentSceneId": "start", "terminal": False},
            "openingGranted": False, "lifecycleApplied": []}


def test_clean_seed_is_accepted_without_mutation():
    current = seed()
    before = deepcopy(current)
    assert validate_clean_ledger(registry(), current, owner_id="trusted-account") is None
    assert current == before


@pytest.mark.parametrize("change", [
    lambda s: s.update(ownerType="anon"),
    lambda s: s.update(ownerId="spoofed"),
    lambda s: s.update(progressionRevision=True),
    lambda s: s.update(progressionRevision=1),
    lambda s: s.update(openingGranted=True),
    lambda s: s.update(lifecycleApplied=["first"]),
    lambda s: s.update(coins={"confirmed": 100}),
    lambda s: s.update(achievements={"FIRST_CHOICE": {"source": "imported"}}),
    lambda s: s["derived"].update(coins=100),
    lambda s: s["derived"]["achievements"].append("FIRST_CHOICE"),
    lambda s: s["derived"]["affinity"].update(friend=99),
    lambda s: s["checkpoint"].pop("contentVersion"),
    lambda s: s["checkpoint"].update(contentVersion=True),
    lambda s: s["checkpoint"].update(contentVersion=2),
    lambda s: s["checkpoint"].update(currentSceneId="missing"),
    lambda s: s["checkpoint"].update(terminal=True),
    lambda s: s.update(fenced=True),
    lambda s: s.update(claimedBy="other"),
])
def test_rejects_modified_seed_without_mutating_it(change):
    current = seed()
    change(current)
    before = deepcopy(current)
    with pytest.raises(InvalidCleanLedger):
        validate_clean_ledger(registry(), current, owner_id="trusted-account")
    assert current == before


def test_missing_registry_version_fails_closed():
    content = registry()
    content["books"]["book1"]["version"] = 2
    with pytest.raises(InvalidCleanLedger):
        validate_clean_ledger(content, seed(), owner_id="trusted-account")


def test_caller_must_supply_authenticated_owner():
    with pytest.raises(InvalidCleanLedger):
        validate_clean_ledger(registry(), seed(), owner_id="")
