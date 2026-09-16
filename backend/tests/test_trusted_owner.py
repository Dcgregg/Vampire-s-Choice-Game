"""Pure tests for the inert progression ownership boundary."""

import pytest

from progression.trusted_owner import ProgressionAccessDenied, require_account_ledger_owner


def ledger(**changes):
    value = {"_id": "ledger-a", "ownerType": "account", "ownerId": "user-a",
             "progressionRevision": 0, "appliedEventIds": {}, "checkpoint": {}}
    value.update(changes)
    return value


def test_verified_owner_can_access_clean_ledger():
    original = ledger()
    result = require_account_ledger_owner(original, authenticated_user_id="user-a")
    assert result == original
    assert result is not original


@pytest.mark.parametrize("identity", ["", " ", None, 123, "user-b", "vc_anonymous123"])
def test_missing_or_other_identity_denied(identity):
    with pytest.raises(ProgressionAccessDenied):
        require_account_ledger_owner(ledger(), authenticated_user_id=identity)


@pytest.mark.parametrize("value", [None, {}, ledger(ownerType="anonymous"),
                                    ledger(ownerId="user-b"), ledger(mergedInto="another"),
                                    ledger(fencedAt="now"), ledger(claimedBy="other"),
                                    ledger(progressionRevision=True), ledger(progressionRevision=-1),
                                    ledger(appliedEventIds=None), ledger(appliedEventIds=[]),
                                    ledger(appliedEventIds="forged")])
def test_missing_foreign_fenced_or_legacy_ledger_denied(value):
    with pytest.raises(ProgressionAccessDenied):
        require_account_ledger_owner(value, authenticated_user_id="user-a")
