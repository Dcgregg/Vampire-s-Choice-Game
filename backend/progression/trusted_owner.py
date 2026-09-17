"""Inert ownership boundary for a future authenticated progression endpoint.

The user ID must come from server-verified session resolution, never a request
body, anonymous player ID, or untrusted save. This guard alone does not validate
story events, awards, or the caller's database permissions.
"""
from __future__ import annotations

from typing import Any, Mapping


class ProgressionAccessDenied(Exception):
    """No authenticated ownership proof for the requested clean ledger."""


def require_account_ledger_owner(ledger: Mapping[str, Any] | None, *, authenticated_user_id: str) -> dict:
    """Return a clean, account-owned ledger or deny without revealing its owner.

    Call only after resolving authenticated_user_id from a verified server
    session. A client-provided user ID is not authentication.
    """
    if not isinstance(authenticated_user_id, str) or not authenticated_user_id.strip():
        raise ProgressionAccessDenied("authenticated account required")
    if not isinstance(ledger, Mapping):
        raise ProgressionAccessDenied("ledger unavailable")
    if ledger.get("ownerType") != "account" or ledger.get("ownerId") != authenticated_user_id:
        raise ProgressionAccessDenied("ledger unavailable")
    if ledger.get("fenced") or any(ledger.get(field) is not None for field in ("mergedInto", "fencedAt", "claimedBy")):
        raise ProgressionAccessDenied("ledger unavailable")
    if type(ledger.get("progressionRevision")) is not int or ledger["progressionRevision"] < 0:
        raise ProgressionAccessDenied("ledger unavailable")
    if not isinstance(ledger.get("appliedEventIds"), dict):
        raise ProgressionAccessDenied("ledger unavailable")
    return dict(ledger)
