"""Inert account-only opening grant; NOT registered with the live API.

The owner ID must be resolved by server authentication. The caller must load
trusted content and install a UNIQUE (ownerType, ownerId) index beforehand.
Never pass a browser save, import legacy coins, or use this as a reward retry.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from pymongo.errors import DuplicateKeyError

from .clean_initializer import clean_seed
from .clean_ledger import InvalidCleanLedger

OPENING_BLOOD_COINS = 50
_OWNER_INDEX = [("ownerType", 1), ("ownerId", 1)]


async def _require_unique_owner_index(ledgers: Any) -> None:
    """Do not issue coins without a full, unique account-owner index."""
    indexes = await ledgers.index_information()
    if not any(
        index.get("unique") is True
        and index.get("key") == _OWNER_INDEX
        and not index.get("sparse")
        and not index.get("partialFilterExpression")
        for index in indexes.values()
    ):
        raise InvalidCleanLedger("unique account owner index required for opening grant")


async def initialize_granted_account_ledger(
    ledgers: Any, registry: Mapping[str, Any], *, owner_id: str,
    book_id: str, content_version: int, scene_id: str,
) -> dict:
    """Atomically create a new account ledger with one 50-coin grant.

    Existing ledgers are returned unchanged: no backfill, replay, migration or
    second grant. A preinstalled unique owner index resolves concurrent inserts.
    A separate reviewed flow is required to handle previously created clean,
    unawarded ledgers and to preserve existing story progress.
    """
    if not isinstance(owner_id, str) or not owner_id.strip():
        raise InvalidCleanLedger("missing authenticated account owner")
    await _require_unique_owner_index(ledgers)
    query = {"ownerType": "account", "ownerId": owner_id}
    existing = await ledgers.find_one(query)
    if existing is not None:
        return deepcopy(existing)
    seed = clean_seed(registry, owner_id=owner_id, book_id=book_id,
                      content_version=content_version, scene_id=scene_id)
    seed["coins"] = {"confirmed": OPENING_BLOOD_COINS}
    seed["derived"]["coins"] = OPENING_BLOOD_COINS
    seed["openingGranted"] = True
    try:
        await ledgers.insert_one(deepcopy(seed))
    except DuplicateKeyError:
        existing = await ledgers.find_one(query)
        if existing is None:
            raise InvalidCleanLedger("duplicate opening grant cannot be reconciled")
        return deepcopy(existing)
    return deepcopy(seed)
