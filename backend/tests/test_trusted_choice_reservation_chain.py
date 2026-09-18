"""Pure, inert multi-revision choice planning regressions; no database or live routes."""
from copy import deepcopy
from uuid import uuid4

import pytest

from progression.choice_checkpoint_guard import CheckpointConflict
from progression.trusted_choice_reservation import plan_account_choice_reservation
from test_choice_checkpoint_guard import event, ledger, registry


def test_second_choice_uses_durable_first_result_and_rejects_prior_event_id():
    first_id, second_id = str(uuid4()), str(uuid4())
    original = {
        **ledger(), "_id": "ledger-a", "ownerType": "account", "ownerId": "account-a",
        "appliedEventIds": {"3": str(uuid4())},
    }
    before = deepcopy(original)
    first = plan_account_choice_reservation(
        registry(), original, event(eventId=first_id), authenticated_user_id="account-a",
    )
    assert original == before
    assert first["base_revision"] == 3
    assert first["awards"] == {"coins": 10, "achievements": []}
    # Simulate only the durable fields that the attributed adapter would write.
    # This is NOT a substitute for a Mongo transaction/integration test.
    committed = {
        **deepcopy(original), **deepcopy(first["next_projection"]),
        "progressionRevision": 4,
        "appliedEventIds": {**original["appliedEventIds"], "4": first_id},
    }
    second_event = event(
        eventId=second_id, baseProgressionRevision=4,
        fromSceneId="next", choiceId="noncurrent",
    )
    second = plan_account_choice_reservation(
        registry(), committed, second_event, authenticated_user_id="account-a",
    )
    assert second["base_revision"] == 4
    assert second["expected_checkpoint"] == committed["checkpoint"]
    assert second["awards"] == {"coins": 500, "achievements": []}
    assert second["next_projection"]["coins"]["confirmed"] == 530
    assert committed["coins"]["confirmed"] == 30
    with pytest.raises(CheckpointConflict, match="already attributed"):
        plan_account_choice_reservation(
            registry(), committed, event(
                eventId=first_id, baseProgressionRevision=4,
                fromSceneId="next", choiceId="noncurrent",
            ), authenticated_user_id="account-a",
        )
