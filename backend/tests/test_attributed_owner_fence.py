"""Pure regressions for authenticated-owner fencing on attributed writes."""

import pytest

from progression.attributed_ledger_write import write_attributed_revision
from progression.attribution import AttributionUnproven


CHECKPOINT = {
    "bookId": "book1", "contentVersion": 1,
    "currentSceneId": "start", "terminal": False,
}
PROJECTION = {
    "coins": {"confirmed": 10}, "achievements": {}, "derived": {},
    "checkpoint": {**CHECKPOINT, "currentSceneId": "next"},
}


class CapturingLedgers:
    def __init__(self, *, matched=True):
        self.matched = matched
        self.filter = None

    async def find_one_and_update(self, filt, update, **_kwargs):
        self.filter = filt
        if not self.matched:
            return None
        return {
            "_id": "ledger-a", "ownerType": "account", "ownerId": "account-a",
            "progressionRevision": 1, "appliedEventIds": {"1": "event-a"},
            **PROJECTION,
        }


def event(**changes):
    return {
        "ledgerId": "ledger-a", "eventId": "event-a",
        "baseRevision": 0, "targetRevision": 1,
        "expectedOwnerType": "account", "expectedOwnerId": "account-a",
        **changes,
    }


@pytest.mark.asyncio
async def test_write_cas_includes_authenticated_owner_identity():
    ledgers = CapturingLedgers()
    result = await write_attributed_revision(
        ledgers, event=event(), projection=PROJECTION,
        expected_checkpoint=CHECKPOINT, session=object(),
    )
    assert result["progressionRevision"] == 1
    assert ledgers.filter["ownerType"] == "account"
    assert ledgers.filter["ownerId"] == "account-a"


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"expectedOwnerType": None}, {"expectedOwnerType": "anonymous"},
    {"expectedOwnerId": None}, {"expectedOwnerId": ""},
])
async def test_write_rejects_missing_or_nonaccount_owner(changes):
    ledgers = CapturingLedgers()
    with pytest.raises(AttributionUnproven, match="ownership"):
        await write_attributed_revision(
            ledgers, event=event(**changes), projection=PROJECTION,
            expected_checkpoint=CHECKPOINT, session=object(),
        )
    assert ledgers.filter is None


@pytest.mark.asyncio
async def test_owner_mismatch_fails_without_award():
    ledgers = CapturingLedgers(matched=False)
    with pytest.raises(AttributionUnproven, match="CAS did not match"):
        await write_attributed_revision(
            ledgers, event=event(), projection=PROJECTION,
            expected_checkpoint=CHECKPOINT, session=object(),
        )
    assert ledgers.filter["ownerId"] == "account-a"
