"""Isolated clean-ledger initializer. NOT registered with the live API.

Only a trusted caller may supply the authenticated account ID, trusted registry,
and approved opening coordinates. The unique (ownerType, ownerId) index MUST
exist before use. Never use a browser save or call this from event retries.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping
from uuid import uuid4

from pymongo.errors import DuplicateKeyError

from .clean_ledger import InvalidCleanLedger, validate_clean_ledger
from .reducer import new_state
from .trusted_content import UnknownContentVersion, book_entry


def clean_seed(registry: Mapping[str, Any], *, owner_id: str,
               book_id: str, content_version: int, scene_id: str) -> dict:
    """Construct an unawarded seed from trusted content, without I/O."""
    if not isinstance(owner_id, str) or not owner_id.strip():
        raise InvalidCleanLedger("missing authenticated account owner")
    if not isinstance(book_id, str) or not book_id or not isinstance(scene_id, str) or not scene_id:
        raise InvalidCleanLedger("missing approved opening coordinates")
    if type(content_version) is not int or content_version <= 0:
        raise InvalidCleanLedger("invalid opening content version")
    try:
        book = book_entry(registry, book_id, content_version)
        if scene_id not in book["scenes"]:
            raise InvalidCleanLedger("opening scene absent from pinned content")
    except (UnknownContentVersion, KeyError, TypeError, ValueError) as exc:
        raise InvalidCleanLedger("opening content unavailable or malformed") from exc
    seed = {"_id": uuid4().hex, "ownerType": "account", "ownerId": owner_id,
            "progressionRevision": 0, "coins": {"confirmed": 0},
            "achievements": {}, "derived": new_state(registry),
            "checkpoint": {"bookId": book_id, "contentVersion": content_version,
                           "currentSceneId": scene_id, "terminal": False},
            "openingGranted": False, "lifecycleApplied": [],
            "appliedEventIds": {}}
    validate_clean_ledger(registry, seed, owner_id=owner_id)
    return seed


async def initialize_clean_account_ledger(ledgers: Any, registry: Mapping[str, Any], *,
                                          owner_id: str, book_id: str,
                                          content_version: int, scene_id: str) -> dict:
    """Insert once, or return the existing account ledger unchanged.

    Requires a preinstalled UNIQUE index on (ownerType, ownerId). The owner ID
    must come from authentication, never the browser. Existing ledgers are read
    before validating *new* opening content: retired opening content must not
    prevent finding an already-progressed ledger. A trusted caller must still
    separately validate existing ledger state before use. New ledgers require
    valid trusted content. This never imports saves or applies opening awards.
    """
    if not isinstance(owner_id, str) or not owner_id.strip():
        raise InvalidCleanLedger("missing authenticated account owner")
    query = {"ownerType": "account", "ownerId": owner_id}
    existing = await ledgers.find_one(query)
    if existing is not None:
        return deepcopy(existing)
    seed = clean_seed(registry, owner_id=owner_id, book_id=book_id,
                      content_version=content_version, scene_id=scene_id)
    try:
        await ledgers.insert_one(deepcopy(seed))
    except DuplicateKeyError:
        existing = await ledgers.find_one(query)
        if existing is None:
            raise InvalidCleanLedger("duplicate initialization cannot be reconciled")
        return deepcopy(existing)
    return deepcopy(seed)
