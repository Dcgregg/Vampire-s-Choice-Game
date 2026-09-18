"""First-slice tests only: no MongoDB or exactly-once integration claim."""
import pytest

from progression.reservations import (
    Reservation, ReservationDecision as D, can_reserve, decide_retry, payload_digest,
)


def test_payload_digest_is_canonical_and_binds_payload():
    assert payload_digest({"eventId": "e1", "choiceId": "a"}) == payload_digest(
        {"choiceId": "a", "eventId": "e1"})
    assert payload_digest({"eventId": "e1", "choiceId": "a"}) != payload_digest(
        {"eventId": "e1", "choiceId": "b"})


@pytest.mark.parametrize("status,expected", [
    ("received", D.VALIDATE), ("applied", D.RETURN_APPLIED),
    ("rejected", D.RETURN_REJECTED), ("unknown", D.INVARIANT_VIOLATION),
])
def test_noncommitting_status(status, expected):
    assert decide_retry(Reservation("e", "hash", status), "hash", 0) == expected


def test_event_id_cannot_be_reused_with_different_payload():
    assert decide_retry(Reservation("e", "original", "applied"), "changed", 3) == D.PAYLOAD_MISMATCH
    assert decide_retry(Reservation("e", "original", "committing", 1, 2), "changed", 1) == D.PAYLOAD_MISMATCH


@pytest.mark.parametrize("revision,expected", [
    (7, D.COMMIT), (8, D.FINALISE), (68, D.FINALISE), (6, D.INVARIANT_VIOLATION),
])
def test_durable_revision_reservation(revision, expected):
    event = Reservation("e", "hash", "committing", base_revision=7, target_revision=8)
    assert decide_retry(event, "hash", revision) == expected


def test_malformed_reservation_is_never_committed():
    assert decide_retry(Reservation("e", "hash", "committing", 7, 9), "hash", 7) == D.INVARIANT_VIOLATION
    assert decide_retry(Reservation("e", "hash", "committing"), "hash", 7) == D.INVARIANT_VIOLATION


def test_preflight_guards_are_conservative():
    assert can_reserve(ledger_revision=2, submitted_base_revision=2, checkpoint_matches=True,
                       terminal=False, fenced=False)
    for overrides in ({"submitted_base_revision": 1}, {"checkpoint_matches": False},
                      {"terminal": True}, {"fenced": True}):
        args = dict(ledger_revision=2, submitted_base_revision=2, checkpoint_matches=True,
                    terminal=False, fenced=False)
        args.update(overrides)
        assert not can_reserve(**args)
