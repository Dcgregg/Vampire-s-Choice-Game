"""Pure inert reservation planning tests; no real accounts or database."""
from copy import deepcopy

import pytest

from progression.choice_checkpoint_guard import CheckpointConflict
from progression.trusted_choice_reservation import plan_account_choice_reservation
from progression.trusted_content import InvalidChoice
from progression.trusted_owner import ProgressionAccessDenied
from test_choice_checkpoint_guard import event, ledger, registry


def owned_ledger():
    return {**ledger(), "_id": "ledger-a", "ownerType": "account",
            "ownerId": "account-a", "appliedEventIds": {
                "3": "550e8400-e29b-41d4-a716-446655440001"}}


def plan(current, choice=None, identity="account-a"):
    return plan_account_choice_reservation(
        registry(), current, choice or event(), authenticated_user_id=identity,
    )


def test_valid_plan_is_derived_and_does_not_mutate_ledger():
    current = owned_ledger()
    before = deepcopy(current)
    result = plan(current)
    assert current == before
    assert result["ledger_id"] == "ledger-a"
    assert result["expected_owner_type"] == "account"
    assert result["expected_owner_id"] == "account-a"
    assert result["event_id"] == event().eventId
    assert len(result["payload_hash"]) == 64
    assert result["base_revision"] == 3
    assert result["awards"] == {"coins": 10}
    assert result["expected_checkpoint"] == before["checkpoint"]
    assert result["next_projection"]["coins"]["confirmed"] == 30
    result["next_projection"]["coins"]["confirmed"] = 999
    assert current == before


@pytest.mark.parametrize("identity", ["", "account-b", None])
def test_foreign_or_missing_verified_identity_denied(identity):
    with pytest.raises(ProgressionAccessDenied):
        plan(owned_ledger(), identity=identity)


@pytest.mark.parametrize("changes", [
    {"fenced": True}, {"ownerType": "anonymous"}, {"_id": None},
    {"appliedEventIds": {"3": event().eventId}},
    {"appliedEventIds": {}},
    {"appliedEventIds": {"4": "prior"}},
    {"appliedEventIds": {"03": "prior"}},
    {"appliedEventIds": {"3": "prior", "2": "prior"}},
])
def test_rejects_unowned_missing_or_corrupt_attribution(changes):
    current = owned_ledger()
    current.update(changes)
    before = deepcopy(current)
    with pytest.raises((ProgressionAccessDenied, CheckpointConflict)):
        plan(current)
    assert current == before


@pytest.mark.parametrize("changes", [
    {"baseProgressionRevision": 2}, {"fromSceneId": "next"},
    {"choiceId": "unknown"}, {"choiceId": "terminal"},
    {"choiceId": "award"}, {"contentVersion": 2},
])
def test_invalid_or_unsupported_choices_never_produce_reservation(changes):
    with pytest.raises((CheckpointConflict, InvalidChoice)):
        plan(owned_ledger(), event(**changes))


def test_unparsed_choice_payload_cannot_be_planned():
    current = owned_ledger()
    before = deepcopy(current)
    with pytest.raises(CheckpointConflict, match="strictly parsed"):
        plan_account_choice_reservation(
            registry(), current, event().model_dump(mode="python"),
            authenticated_user_id="account-a",
        )
    assert current == before
