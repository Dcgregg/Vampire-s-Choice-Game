"""Candidate attribution contract; no live Mongo writer uses this yet."""
import pytest

from progression.attribution import AttributionUnproven, require_event_attribution


def event():
    return {"ledgerId": "ledger-a", "eventId": "event-a", "baseRevision": 0,
            "targetRevision": 1}


def ledger(revision=1, history=None):
    return {"_id": "ledger-a", "progressionRevision": revision,
            "appliedEventIds": history if history is not None else {"1": "event-a"}}


def test_exact_attribution_at_target_revision():
    require_event_attribution(ledger(), event())


def test_retained_attribution_after_later_legitimate_revision():
    require_event_attribution(ledger(9, {"1": "event-a", "9": "event-later"}), event())


@pytest.mark.parametrize("candidate", [
    {"_id": "ledger-a", "progressionRevision": 1},
    ledger(1, {"1": "foreign-event"}),
    ledger(9, {"9": "foreign-event"}),
    ledger(0),
    {**ledger(), "_id": "ledger-b"},
    {**ledger(), "progressionRevision": True},
])
def test_missing_foreign_or_uncommitted_attribution_fails_closed(candidate):
    with pytest.raises(AttributionUnproven):
        require_event_attribution(candidate, event())


@pytest.mark.parametrize("changes", [
    {"baseRevision": True}, {"targetRevision": 2}, {"eventId": "other"},
    {"ledgerId": "ledger-b"}, {"eventId": ""},
])
def test_malformed_or_mismatched_event_fails_closed(changes):
    with pytest.raises(AttributionUnproven):
        require_event_attribution(ledger(), {**event(), **changes})
