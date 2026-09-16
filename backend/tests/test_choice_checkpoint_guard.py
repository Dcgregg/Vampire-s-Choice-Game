"""Pure checkpoint-guard tests; no API, database or production credentials."""
from copy import deepcopy

import pytest

from progression.choice_checkpoint_guard import CheckpointConflict, prepare_nonterminal_choice
from progression.strict_event_input import StrictChoiceEvent, StrictLifecycleEvent
from progression.trusted_content import InvalidChoice, UnknownContentVersion

UUID4 = "550e8400-e29b-41d4-a716-446655440000"


def registry():
    return {
        "characters": {"friend": 0},
        "rules": {"affinityMin": -100, "affinityMax": 100, "coinsMin": 0,
                  "derivedAchievements": [
                      {"type": "affinityThreshold", "id": "friend_badge", "threshold": 5},
                  ]},
        "books": {"book1": {"version": 1, "scenes": {
            "start": {"choices": {
                "ordinary": {"nextSceneId": "next", "effects": {"coinsChange": 10}},
                "spend_and_change": {"nextSceneId": "next", "effects": {
                    "coinsChange": -50, "setFlags": {"helped": True},
                    "relationshipChanges": {"friend": 2}}},
                "award": {"nextSceneId": "next", "effects": {"achievementId": "badge"}},
                "affinity_award": {"nextSceneId": "next", "effects": {
                    "relationshipChanges": {"friend": 5}}},
                "terminal": {"nextSceneId": "end", "endsBook": True},
                "missing": {"nextSceneId": "missing_scene"},
            }},
            "next": {"choices": {
                "noncurrent": {"nextSceneId": "end", "effects": {"coinsChange": 500}},
            }},
            "end": {"choices": {}},
        }}},
    }


def ledger():
    return {"progressionRevision": 3,
            "checkpoint": {"bookId": "book1", "contentVersion": 1,
                           "currentSceneId": "start", "terminal": False},
            "coins": {"confirmed": 20}, "achievements": {},
            "derived": {"coins": 20, "affinity": {"friend": 0}, "flags": {}, "achievements": []}}


def event(**changes):
    values = {"kind": "choice", "eventId": UUID4, "bookId": "book1",
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
        "bookId": "book1", "contentVersion": 1,
        "currentSceneId": "next", "terminal": False}
    assert proposal["nextProjection"]["coins"]["confirmed"] == 30
    assert proposal["nextProjection"]["derived"]["coins"] == 30
    assert proposal["awarded"] == []
    proposal["expectedCheckpoint"]["currentSceneId"] = "tampered"
    assert current == before


def test_spending_and_non_award_effects_preserve_coin_floor_and_input():
    current = ledger()
    before = deepcopy(current)
    proposal = prepare_nonterminal_choice(registry(), current, event(choiceId="spend_and_change"))
    assert current == before
    assert proposal["nextProjection"]["coins"]["confirmed"] == 0
    assert proposal["nextProjection"]["derived"] == {
        "coins": 0, "affinity": {"friend": 2}, "flags": {"helped": True}, "achievements": []}
    assert proposal["nextProjection"]["checkpoint"]["currentSceneId"] == "next"
    assert proposal["nextProjection"]["checkpoint"]["contentVersion"] == 1
    assert proposal["awarded"] == []
    proposal["nextProjection"]["derived"]["flags"]["helped"] = False
    assert current == before


@pytest.mark.parametrize("event_changes,ledger_changes", [
    ({"baseProgressionRevision": 2}, {}),
    ({"bookId": "other"}, {}),
    ({"fromSceneId": "next", "choiceId": "noncurrent"}, {}),
    ({}, {"fenced": True}),
    ({}, {"mergedInto": "new-ledger"}),
    ({}, {"fencedAt": "2026-09-16T12:00:00Z"}),
    ({}, {"claimedBy": "other-owner"}),
    ({}, {"checkpoint": {"bookId": "book1", "contentVersion": 1,
                         "currentSceneId": "start", "terminal": True}}),
])
def test_rejects_wrong_revision_checkpoint_or_fence_without_mutation(event_changes, ledger_changes):
    current = ledger()
    current.update(ledger_changes)
    before = deepcopy(current)
    with pytest.raises(CheckpointConflict):
        prepare_nonterminal_choice(registry(), current, event(**event_changes))
    assert current == before


@pytest.mark.parametrize("confirmed,derived", [
    (20, 21), (21, 20), (-1, -1), (True, True), (20.0, 20), (20, "20"),
])
def test_rejects_inconsistent_coin_projection_without_mutation(confirmed, derived):
    current = ledger()
    current["coins"]["confirmed"] = confirmed
    current["derived"]["coins"] = derived
    before = deepcopy(current)
    with pytest.raises(CheckpointConflict, match="coin balances"):
        prepare_nonterminal_choice(registry(), current, event())
    assert current == before


@pytest.mark.parametrize("recorded,unlocked", [
    ({"badge": {"unlockedAt": "existing"}}, []),
    ({}, ["badge"]),
    ({"badge": {"unlockedAt": "existing"}}, ["badge", "badge"]),
    ({}, "badge"),
    ([], []),
])
def test_rejects_inconsistent_achievement_projection_without_mutation(recorded, unlocked):
    current = ledger()
    current["achievements"] = recorded
    current["derived"]["achievements"] = unlocked
    before = deepcopy(current)
    with pytest.raises(CheckpointConflict, match="achievements disagree"):
        prepare_nonterminal_choice(registry(), current, event())
    assert current == before


def test_existing_matching_achievement_projection_is_preserved():
    current = ledger()
    current["achievements"] = {"badge": {"unlockedAt": "existing"}}
    current["derived"]["achievements"] = ["badge"]
    before = deepcopy(current)
    proposal = prepare_nonterminal_choice(registry(), current, event())
    assert current == before
    assert proposal["nextProjection"]["achievements"] == before["achievements"]
    assert proposal["nextProjection"]["derived"]["achievements"] == ["badge"]
    assert proposal["awarded"] == []


@pytest.mark.parametrize("choice_id,exception", [
    ("award", CheckpointConflict), ("affinity_award", CheckpointConflict),
    ("terminal", CheckpointConflict), ("missing", InvalidChoice),
    ("unknown", InvalidChoice),
])
def test_rejects_unsupported_or_invalid_choices_without_mutation(choice_id, exception):
    current = ledger()
    before = deepcopy(current)
    with pytest.raises(exception):
        prepare_nonterminal_choice(registry(), current, event(choiceId=choice_id))
    assert current == before


@pytest.mark.parametrize("pin", [None, 0, -1, True, 1.0, "1", 2])
def test_rejects_missing_invalid_or_mismatched_durable_pin_without_mutation(pin):
    current = ledger()
    if pin is None:
        del current["checkpoint"]["contentVersion"]
    else:
        current["checkpoint"]["contentVersion"] = pin
    before = deepcopy(current)
    with pytest.raises(CheckpointConflict, match="durable content version"):
        prepare_nonterminal_choice(registry(), current, event())
    assert current == before


def test_rejects_valid_registry_version_when_it_differs_from_durable_pin():
    current = ledger()
    current["checkpoint"]["contentVersion"] = 2
    available = registry()
    available["books"]["book1"]["version"] = 2
    with pytest.raises(CheckpointConflict, match="durable content version"):
        prepare_nonterminal_choice(available, current, event(contentVersion=1))


def test_rejects_unavailable_pinned_content_version():
    current = ledger()
    current["checkpoint"]["contentVersion"] = 2
    with pytest.raises(UnknownContentVersion):
        prepare_nonterminal_choice(registry(), current, event(contentVersion=2))


def test_rejects_lifecycle_event():
    lifecycle = StrictLifecycleEvent(kind="lifecycle", eventId=UUID4, bookId="book1",
                                     contentVersion=1, baseProgressionRevision=3,
                                     lifecycleId="start")
    with pytest.raises(CheckpointConflict):
        prepare_nonterminal_choice(registry(), ledger(), lifecycle)
