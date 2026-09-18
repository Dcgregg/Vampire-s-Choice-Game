"""Pure inert reservation planning tests; no real accounts or database."""
from copy import deepcopy

import pytest

from progression.choice_checkpoint_guard import CheckpointConflict
from progression.strict_event_input import StrictLifecycleEvent
from progression.trusted_choice_reservation import (
    plan_account_choice_reservation, plan_account_lifecycle_reservation,
)
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
    assert result["awards"] == {"coins": 10, "achievements": []}
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
    {"choiceId": "unknown"}, {"contentVersion": 2},
])
def test_invalid_choices_never_produce_reservation(changes):
    with pytest.raises((CheckpointConflict, InvalidChoice)):
        plan(owned_ledger(), event(**changes))


def test_achievement_and_terminal_choices_produce_atomic_reservations():
    award = plan_account_choice_reservation(
        registry(), owned_ledger(), event(choiceId="award"),
        authenticated_user_id="account-a", unlocked_at=456,
    )
    assert award["awards"] == {"coins": 0, "achievements": ["badge"]}
    assert award["next_projection"]["achievements"]["badge"] == {
        "unlockedAt": 456, "source": "awarded",
    }
    terminal = plan(owned_ledger(), event(choiceId="terminal"))
    assert terminal["next_projection"]["checkpoint"]["terminal"] is True


def test_unparsed_choice_payload_cannot_be_planned():
    current = owned_ledger()
    before = deepcopy(current)
    with pytest.raises(CheckpointConflict, match="strictly parsed"):
        plan_account_choice_reservation(
            registry(), current, event().model_dump(mode="python"),
            authenticated_user_id="account-a",
        )
    assert current == before


def test_character_created_plan_is_atomic_and_replay_scoped():
    current = owned_ledger()
    current["progressionRevision"] = 0
    current["appliedEventIds"] = {}
    current["lifecycleApplied"] = []
    lifecycle = StrictLifecycleEvent(
        kind="lifecycle", eventId=event().eventId, bookId="book1",
        contentVersion=1, baseProgressionRevision=0,
        lifecycleId="character_created",
    )
    result = plan_account_lifecycle_reservation(
        registry(), current, lifecycle,
        authenticated_user_id="account-a", unlocked_at=789,
        opening_book_id="book1", opening_content_version=1,
        opening_scene_id="start",
    )
    assert result["awards"] == {"coins": 0, "achievements": ["story_started"]}
    assert result["next_projection"]["achievements"]["story_started"] == {
        "unlockedAt": 789, "source": "awarded",
    }
    assert result["next_projection"]["lifecycleApplied"] == [
        "book1:1:character_created",
    ]
