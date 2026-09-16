"""Inert Phase 6B recovery sweep; no scheduler or live route is wired.

Call only from a trusted maintenance worker after indexes and durable writes
are configured. Never discard an unresolved reservation automatically.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .mongo_reservations import ProgressionConflict, ReservationBusy, ReservationInvariantError


@dataclass(frozen=True)
class SweepResult:
    examined: int = 0
    applied: int = 0
    busy: int = 0
    conflicted: int = 0
    invalid: int = 0


async def sweep_expired(store, *, limit: int = 100) -> SweepResult:
    """Attempt at most `limit` expired events; failures remain for investigation.

    A fixed cutoff and a deterministic order make the scan bounded. Another
    worker may acquire a lease after selection; recover() owns the final CAS.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0 or limit > 1000:
        raise ValueError("limit must be an integer between 1 and 1000")
    cutoff = datetime.now(timezone.utc)
    cursor = store.events.find({"status": "committing", "leaseUntil": {"$lte": cutoff}}).sort(
        [("leaseUntil", 1), ("_id", 1)]
    ).limit(limit)
    examined = applied = busy = conflicted = invalid = 0
    async for event in cursor:
        examined += 1
        try:
            result = await store.recover(event)
        except ReservationBusy:
            busy += 1
        except ProgressionConflict:
            conflicted += 1
        except ReservationInvariantError:
            invalid += 1
        else:
            if result.get("status") != "applied":
                raise ReservationInvariantError("recovery returned a non-applied event")
            applied += 1
    return SweepResult(examined, applied, busy, conflicted, invalid)
