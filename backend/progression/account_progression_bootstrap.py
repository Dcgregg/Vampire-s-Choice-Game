"""Authenticated account-ledger bootstrap; inert until its route is registered.

This service creates only a clean, server-owned ledger with the approved
50-BloodCoin opening grant and fresh achievements. Narrative saves are handled
separately and can never seed this ledger's rewards.
"""
from __future__ import annotations

from typing import Any, Mapping

from .clean_ledger import InvalidCleanLedger
from .opening_grant import OPENING_BLOOD_COINS, initialize_granted_account_ledger
from .trusted_choice_service import TrustedChoiceIndeterminate, public_account_ledger
from .trusted_owner import ProgressionAccessDenied, require_account_ledger_owner


class AccountProgressionUnavailable(Exception):
    """Bootstrap could not establish a valid granted account ledger."""


async def bootstrap_account_progression(
    ledgers: Any, registry: Mapping[str, Any], *, authenticated_user_id: str,
    book_id: str, content_version: int, scene_id: str,
) -> dict:
    """Create once or return the existing authenticated trusted ledger.

    Existing unawarded or malformed ledgers are never silently repaired or
    granted. They require an explicit reviewed migration because a blind grant
    could duplicate value or bless untrusted state.
    """
    try:
        ledger = await initialize_granted_account_ledger(
            ledgers, registry, owner_id=authenticated_user_id,
            book_id=book_id, content_version=content_version, scene_id=scene_id,
        )
        owned = require_account_ledger_owner(
            ledger, authenticated_user_id=authenticated_user_id,
        )
        if owned.get("openingGranted") is not True:
            raise AccountProgressionUnavailable(
                "existing ledger has no verified opening grant",
            )
        public = public_account_ledger(owned)
        if (owned.get("progressionRevision") == 0
                and public["coins"]["confirmed"] != OPENING_BLOOD_COINS):
            raise AccountProgressionUnavailable(
                "fresh ledger does not contain the approved opening grant",
            )
        return public
    except AccountProgressionUnavailable:
        raise
    except (InvalidCleanLedger, ProgressionAccessDenied,
            TrustedChoiceIndeterminate, TypeError, ValueError) as exc:
        raise AccountProgressionUnavailable(
            "trusted account progression unavailable",
        ) from exc
