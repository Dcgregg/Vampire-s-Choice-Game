"""Pure validation of an *unawarded initial* account ledger; no I/O or creation.

This is not a general validator for progressed ledgers, an initializer, or an
authorization check. The caller must independently authenticate owner_id and
load the registry from a trusted source. Never pass browser-supplied saves.
"""
from collections.abc import Mapping
from typing import Any

from .reducer import new_state
from .trusted_content import UnknownContentVersion, book_entry


class InvalidCleanLedger(ValueError):
    """A purported fresh account ledger violates the approved seed invariants."""


def validate_clean_ledger(registry: Mapping[str, Any], ledger: Mapping[str, Any], *, owner_id: str) -> None:
    """Fail closed on malformed or pre-awarded seed data; return no projection.

    This deliberately validates only the approved *initial* state (revision 0).
    Operational fields such as Mongo _id and timestamps are outside this pure
    validator; no database indexes, uniqueness or identity are established here.
    """
    if not isinstance(ledger, Mapping) or not isinstance(owner_id, str) or not owner_id:
        raise InvalidCleanLedger("missing trusted account owner")
    if ledger.get("ownerType") != "account" or ledger.get("ownerId") != owner_id:
        raise InvalidCleanLedger("account owner mismatch")
    if type(ledger.get("progressionRevision")) is not int or ledger["progressionRevision"] != 0:
        raise InvalidCleanLedger("initial revision must be zero")
    if ledger.get("openingGranted") is not False or ledger.get("lifecycleApplied") != []:
        raise InvalidCleanLedger("initial awards or lifecycle markers are not empty")
    if ledger.get("achievements") != {} or ledger.get("coins") != {"confirmed": 0}:
        raise InvalidCleanLedger("initial confirmed rewards must be empty")
    checkpoint = ledger.get("checkpoint")
    if not isinstance(checkpoint, Mapping):
        raise InvalidCleanLedger("missing checkpoint")
    book_id = checkpoint.get("bookId")
    scene_id = checkpoint.get("currentSceneId")
    version = checkpoint.get("contentVersion")
    if (not isinstance(book_id, str) or not book_id or not isinstance(scene_id, str)
            or not scene_id or type(version) is not int or version <= 0
            or checkpoint.get("terminal") is not False):
        raise InvalidCleanLedger("invalid initial checkpoint or content pin")
    try:
        book = book_entry(registry, book_id, version)
        if scene_id not in book["scenes"]:
            raise InvalidCleanLedger("initial scene absent from pinned content")
    except (UnknownContentVersion, KeyError, TypeError, ValueError) as exc:
        raise InvalidCleanLedger("unavailable or malformed trusted content") from exc
    # Equality checks are intentional: no imported rewards, extra derived fields,
    # or client-controlled values may be smuggled into a clean seed.
    if ledger.get("derived") != new_state(registry):
        raise InvalidCleanLedger("initial derived state differs from trusted seed")
    if any(ledger.get(key) is not None for key in ("mergedInto", "fencedAt", "claimedBy")) or ledger.get("fenced"):
        raise InvalidCleanLedger("initial ledger is fenced or claimed")
