"""Failure-policy guard for the inert Phase 6B recovery sweep."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from progression.recovery_sweep import sweep_expired


class _Cursor:
    def __init__(self, events):
        self.events = events

    def sort(self, _order):
        return self

    def limit(self, count):
        self.events = self.events[:count]
        return self

    def __aiter__(self):
        self._iterator = iter(self.events)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration:
            raise StopAsyncIteration


@pytest.mark.asyncio
async def test_unexpected_database_error_aborts_sweep_without_processing_later_events():
    """Do not swallow an infrastructure error or silently advance the batch."""
    events = [{"_id": "first"}, {"_id": "second"}]
    store = MagicMock()
    store.events.find.return_value = _Cursor(events)
    attempted = []

    async def recover(event):
        attempted.append(event["_id"])
        raise RuntimeError("simulated database outage")

    store.recover = recover
    with pytest.raises(RuntimeError, match="simulated database outage"):
        await sweep_expired(store, limit=2)
    assert attempted == ["first"]
    store.events.find.assert_called_once()
    query = store.events.find.call_args.args[0]
    assert query["status"] == "committing"
    assert isinstance(query["leaseUntil"]["$lte"], datetime)
    assert query["leaseUntil"]["$lte"].tzinfo == timezone.utc
