"""Pure checkpoint-guard tests; no API, database or production credentials."""
from copy import deepcopy

import pytest

from progression.choice_checkpoint_guard import CheckpointConflict, prepare_nonterminal_choice
from progression.strict_event_input import StrictChoiceEvent, StrictLifecycleEvent
from progression.trusted_content import InvalidChoice, UnknownContentVersion


def registry():
    return {
        "characters": {},
        "rules": {"affinityMin": -100, "affinityMax": 100, "coinsMin": 0,
                  "derivedAchievements": []},
        "books": {"book1": {"version": 1, "scenes": {
            "start": {"choices": {
                "ordinary": {"nextSceneId": "next", "effects": {"coinsChange": 10}},
                "award": {"nextSceneId": "next", "effects": {"achievementId": "badge"}},
                "terminal": {"nextSceneId": "end", "endsBook": True},
                "missing": {"nextSceneId": "missing_scene"},
            }},
            "next": {"choices": {}},
            "end": {"choices": {}},
        }}},
    }


def ledger():
    return {"progressionRevision": 3,
            "checkpoint": {"bookId": "book1", "currentSceneId": "start", "terminal": False},
            "coins": {"confirmed": 20}, "achievements": {},
            "derived": {"coins": 20, "affinity": {}, "flags": {}, "achievements": []}}


def event(**changes):
    values = {"kind": "choice", "eventId": "evt_1", "bookId": "book1",
              "contentVersion": 1, "baseProgressionRevision": 3,
              "fromSceneId": "start", "choiceId": "ordinary"}
    values.update(changes)
    return StrictChoiceEvent.model_validate(values)


def test_ordinary_choice_returns_proposal_without_mutation():
    current = ledger()
    before = deepcopy(current)
    proposal = prepare_nonterminal_choice(registry(), current, event())
    assert current == before
    assert proposal["expectedCheckpoint"] == before["checkpoint"]
    assert proposal["nextProjection"]["checkpoint"] == {
        "bookId": "book1", "currentSceneId": "next", "terminal": False}
    assert proposal["nextProjection"]["coins"]["confirmed"] == 30
    assert proposal["nextProjection"]["derived"]["coins"] == 30
    assert proposal["awarded"] == []
    proposal["expectedCheckpoint"]["currentSceneId"] = "tampered"
    assert current == before


@pytest.mark.parametrize("event_changes,ledger_changes", [
    ({"baseProgressionRevision": 2}, {}),
    ({"bookId": "other"}, {}),
    ({"fromSceneId": "next"}, {}),
    ({}, {"fenced": True}),
    ({}, {"checkpoint": {"bookId": "book1", "currentSceneId": "start", "terminal": True}}),
])
def test_rejects_wrong_revision_checkpoint_or_fence_without_mutation(event_changes, ledger_changes):
    current = ledger()
    current.update(ledger_changes)
    before = deepcopy(current)
    with pytest.raises(CheckpointConflict):
        prepare_nonterminal_choice(registry(), current, event(**event_changes))
    assert current == before


@pytest.mark.parametrize("choice_id,exception", [
    ("award", CheckpointConflict), ("terminal", CheckpointConflict),
    ("missing", InvalidChoice), ("unknown", InvalidChoice),
])
def test_rejects_unsupported_or_invalid_choices_without_mutation(choice_id, exception):
    current = ledger()
    before = deepcopy(current)
    with pytest.raises(exception):
        prepare_nonterminal_choice(registry(), current, event(choiceId=choice_id))
    assert current == before


def test_rejects_unpinned_content_version():
    with pytest.raises(UnknownContentVersion):
        prepare_nonterminal_choice(registry(), ledger(), event(contentVersion=2))


def test_rejects_lifecycle_event():
    lifecycle = StrictLifecycleEvent(kind="lifecycle", eventId="evt_2", bookId="book1",
                                     contentVersion=1, baseProgressionRevision=3,
                                     lifecycleId="start")
    with pytest.raises(CheckpointConflict):
        prepare_nonterminal_choice(registry(), ledger(), lifecycle)
