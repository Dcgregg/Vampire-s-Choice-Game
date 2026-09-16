"""Pure input-boundary tests: no API, credentials or database."""
import pytest
from pydantic import TypeAdapter, ValidationError

from progression.strict_event_input import StrictProgressionEvent

adapter = TypeAdapter(StrictProgressionEvent)


def choice(**changes):
    event = {"kind": "choice", "eventId": "evt_1", "bookId": "book1",
             "contentVersion": 1, "baseProgressionRevision": 0,
             "fromSceneId": "scene1", "choiceId": "choice1"}
    event.update(changes)
    return event


def test_accepts_only_known_choice_and_lifecycle_fields():
    assert adapter.validate_python(choice()).kind == "choice"
    lifecycle = {"kind": "lifecycle", "eventId": "evt_2", "bookId": "book1",
                 "contentVersion": 1, "baseProgressionRevision": 0,
                 "lifecycleId": "start"}
    assert adapter.validate_python(lifecycle).kind == "lifecycle"


@pytest.mark.parametrize("changes", [
    {"coins": 999}, {"awards": {}}, {"projection": {}}, {"ownerId": "other"},
    {"nextSceneId": "win"}, {"baseProgressionRevision": True},
    {"baseProgressionRevision": "0"}, {"baseProgressionRevision": -1},
    {"contentVersion": False}, {"contentVersion": 0},
    {"eventId": ""}, {"eventId": "x" * 129}, {"eventId": "bad id"},
    {"choiceId": "x" * 129}, {"kind": "admin"},
])
def test_rejects_untrusted_or_malformed_choice(changes):
    with pytest.raises(ValidationError):
        adapter.validate_python(choice(**changes))


def test_requires_explicit_base_revision_and_discriminant():
    for missing in ("baseProgressionRevision", "kind", "choiceId"):
        event = choice()
        del event[missing]
        with pytest.raises(ValidationError):
            adapter.validate_python(event)


def test_lifecycle_cannot_smuggle_choice_fields():
    event = {"kind": "lifecycle", "eventId": "evt_2", "bookId": "book1",
             "contentVersion": 1, "baseProgressionRevision": 0,
             "lifecycleId": "start", "choiceId": "free_award"}
    with pytest.raises(ValidationError):
        adapter.validate_python(event)
