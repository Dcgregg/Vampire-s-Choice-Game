"""Phase 6B first slice: pure decisions for a durable revision reservation.

NOT a database implementation or a live API. The eventual Mongo adapter MUST
create unique indexes on (ledgerId,eventId) and partial (ledgerId,targetRevision),
reserve before advancing the ledger, and use a single conditional ledger write.
This module deliberately does not claim exactly-once persistence on its own.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class ReservationDecision(str, Enum):
    COMMIT = "commit"
    FINALISE = "finalise"
    CONFLICT = "conflict"
    PAYLOAD_MISMATCH = "event_id_payload_mismatch"
    RETURN_APPLIED = "return_applied"
    RETURN_REJECTED = "return_rejected"
    VALIDATE = "validate"
    INVARIANT_VIOLATION = "invariant_violation"


@dataclass(frozen=True)
class Reservation:
    event_id: str
    payload_hash: str
    status: str
    base_revision: int | None = None
    target_revision: int | None = None


def payload_digest(payload: Mapping[str, Any]) -> str:
    """Bind an event ID to canonical payload bytes, independent of key order."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def decide_retry(reservation: Reservation, incoming_hash: str, ledger_revision: int) -> ReservationDecision:
    """Decide from durable reservation and monotonic ledger revision only.

    This is valid ONLY when every ledger revision is reserved exclusively by
    one event, and no other path increments progressionRevision. A committing
    reservation must never be deleted/reassigned, even after finalisation.
    """
    if reservation.payload_hash != incoming_hash:
        return ReservationDecision.PAYLOAD_MISMATCH
    if reservation.status == "applied":
        return ReservationDecision.RETURN_APPLIED
    if reservation.status == "rejected":
        return ReservationDecision.RETURN_REJECTED
    if reservation.status == "received":
        return ReservationDecision.VALIDATE
    if reservation.status != "committing":
        return ReservationDecision.INVARIANT_VIOLATION
    base, target = reservation.base_revision, reservation.target_revision
    if base is None or target is None or base < 0 or target != base + 1:
        return ReservationDecision.INVARIANT_VIOLATION
    if ledger_revision < base:
        return ReservationDecision.INVARIANT_VIOLATION
    if ledger_revision == base:
        return ReservationDecision.COMMIT
    if ledger_revision >= target:
        return ReservationDecision.FINALISE
    return ReservationDecision.INVARIANT_VIOLATION


def can_reserve(*, ledger_revision: int, submitted_base_revision: int, checkpoint_matches: bool,
                terminal: bool, fenced: bool) -> bool:
    """Preflight only; Mongo must repeat these guards in its atomic update."""
    return (ledger_revision >= 0 and ledger_revision == submitted_base_revision
            and checkpoint_matches and not terminal and not fenced)
