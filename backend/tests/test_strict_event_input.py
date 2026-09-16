"""Pure input-boundary tests: no API, credentials or database."""
import pytest
from pydantic import TypeAdapter, ValidationError

from progression.strict_event_input import StrictProgressionEvent

adapter = TypeAdapter(StrictProgressionEvent)
UUID4 = "550e8400-e29b-41d4-a716-446655440000"
OTHER_UUID4 = "550e8400-e29b-41d4-a716-446655440001"


def choice(**changes):
    event = {"kind": "choice", "eventId": UUID4, "bookId": "book1",
             "contentVersion": 1, "baseProgressionRevision": 0,
             "fromSceneId": "scene1", "choiceId": "choice1"}
    event.update(changes)
    return event


def test_accepts_only_known_choice_and_lifecycle_fields():
    assert adapter.validate_python(choice()).kind == "choice"
    lifecycle = {"kind": "lifecycle", "eventId": OTHER_UUID4, "bookId": "book1",
                 "contentVersion": 1, "baseProgressionRevision": 0,
                 "lifecycleId": "start"}
    assert adapter.validate_python(lifecycle).kind == "lifecycle"


@pytest.mark.parametrize("changes", [
    {"coins": 999}, {"awards": {}}, {"projection": {}}, {"ownerId": "other"},
    {"nextSceneId": "win"}, {"baseProgressionRevision": True},
    {"baseProgressionRevision": "0"}, {"baseProgressionRevision": -1},
    {"contentVersion": False}, {"contentVersion": 0},
    {"eventId": ""}, {"eventId": "x" * 129}, {"eventId": "bad id"},
    {"eventId": "evt_1"}, {"eventId": "550e8400-e29b-11d4-a716-446655440000"},
    {"eventId": "550E8400-E29B-41D4-A716-446655440000"},
    {"eventId": "550e8400e29b41d4a716446655440000"},
    {"eventId": "550e8400-e29b-41d4-7716-446655440000"},
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


def test_lifecycle_cannot_smuggle_choice_fields_or_invalid_id():
    event = {"kind": "lifecycle", "eventId": OTHER_UUID4, "bookId": "book1",
             "contentVersion": 1, "baseProgressionRevision": 0,
             "lifecycleId": "start", "choiceId": "free_award"}
    with pytest.raises(ValidationError):
        adapter.validate_python(event)
    del event["choiceId"]
    event["eventId"] = "evt_2"
    with pytest.raises(ValidationError):
        adapter.validate_python(event)
