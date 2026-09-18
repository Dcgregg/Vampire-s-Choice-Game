"""Pure canonicalization fixtures; no API, ledger or production credentials."""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from progression.canonical_event import canonical_event_bytes, canonical_event_sha256


CHOICE = {"kind": "choice", "eventId": "550e8400-e29b-41d4-a716-446655440000",
          "bookId": "book1", "contentVersion": 1, "baseProgressionRevision": 0,
          "fromSceneId": "scene1", "choiceId": "choice1"}
EXPECTED = (b'{"baseProgressionRevision":0,"bookId":"book1","choiceId":"choice1",'
            b'"contentVersion":1,"eventId":"550e8400-e29b-41d4-a716-446655440000",'
            b'"fromSceneId":"scene1","kind":"choice"}')
DIGEST = "65bf7da64655a7c6a48fa3126c3864b2722a239e5cd86eacd50a3b48d87e8b7c"


def test_choice_fixed_utf8_bytes_and_sha256_without_input_mutation():
    before = deepcopy(CHOICE)
    assert canonical_event_bytes(CHOICE) == EXPECTED
    assert canonical_event_sha256(CHOICE) == DIGEST
    assert CHOICE == before
    assert canonical_event_bytes(dict(reversed(list(CHOICE.items())))) == EXPECTED


def test_non_ascii_is_utf8_not_escaped_and_lifecycle_is_distinct():
    lifecycle = {"kind": "lifecycle", "eventId": CHOICE["eventId"],
                 "bookId": "café", "contentVersion": 1,
                 "baseProgressionRevision": 0, "lifecycleId": "start"}
    result = canonical_event_bytes(lifecycle)
    assert b'"bookId":"caf\xc3\xa9"' in result
    assert b"\\u00e9" not in result
    assert canonical_event_sha256(lifecycle) != DIGEST


@pytest.mark.parametrize("invalid", [
    "evt_1", "550e8400-e29b-11d4-a716-446655440000",
    "550E8400-E29B-41D4-A716-446655440000",
    "550e8400e29b41d4a716446655440000",
    "550e8400-e29b-41d4-7716-446655440000",
])
def test_rejects_noncanonical_or_non_v4_event_ids(invalid):
    # The strict input model now rejects these before the helper's defensive check.
    with pytest.raises(ValidationError):
        canonical_event_bytes({**CHOICE, "eventId": invalid})


@pytest.mark.parametrize("changes", [
    {"coins": 999}, {"baseProgressionRevision": True},
    {"contentVersion": "1"}, {"choiceId": None},
])
def test_rejects_unknown_or_coerced_fields(changes):
    with pytest.raises(ValidationError):
        canonical_event_bytes({**CHOICE, **changes})


def test_payload_changes_affect_digest_and_model_instances_are_supported():
    from progression.strict_event_input import StrictChoiceEvent
    assert canonical_event_sha256({**CHOICE, "choiceId": "choice2"}) != DIGEST
    assert canonical_event_bytes(StrictChoiceEvent.model_validate(CHOICE)) == EXPECTED
