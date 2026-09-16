"""Opt-in story-only claim service; NOT wired to the live API.

The caller must resolve user_id from a verified server session, not a request
body. This preserves narrative save fields, never imports client rewards into
trusted progression, and does not create or modify an authoritative ledger.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from pymongo.errors import DuplicateKeyError

from .story_only_transfer import story_only_player_state


class StoryClaimConflict(ValueError):
    """Claim needs explicit resolution, or another writer won the race."""


class StoryClaimDenied(ValueError):
    """Anonymous save is missing or belongs to another account."""


async def claim_story_only(
    anonymous_saves: Any, account_saves: Any, *, authenticated_user_id: str,
    player_id: str, expected_anonymous_revision: int, now: str,
) -> dict:
    """Claim one server-stored anonymous save into a NEW account save.

    An existing account save is never overwritten. Fencing happens first; if
    insertion fails, retrying for the same account can recover the claim.
    This is a migration building block, not an API handler or reward writer.
    """
    if not isinstance(authenticated_user_id, str) or not authenticated_user_id.strip():
        raise StoryClaimDenied("authenticated account required")
    if not isinstance(player_id, str) or not player_id.startswith("vc_"):
        raise StoryClaimDenied("invalid anonymous player identifier")
    if (not isinstance(expected_anonymous_revision, int)
            or isinstance(expected_anonymous_revision, bool)
            or expected_anonymous_revision < 1):
        raise StoryClaimConflict("invalid anonymous revision")
    if not isinstance(now, str) or not now:
        raise StoryClaimConflict("timestamp required")

    anon = await anonymous_saves.find_one({"playerId": player_id})
    if anon is None:
        raise StoryClaimDenied("anonymous save not found")
    if anon.get("claimedBy") not in (None, authenticated_user_id):
        raise StoryClaimDenied("anonymous save belongs to another account")
    if anon.get("revision") != expected_anonymous_revision:
        raise StoryClaimConflict("anonymous save revision changed")
    # Validate and strip rewards BEFORE claiming, so bad input cannot fence a save.
    story = story_only_player_state(anon.get("playerState"))
    existing = await account_saves.find_one({"userId": authenticated_user_id})
    if existing is not None:
        # The initial anonymous read may predate another request's successful
        # claim. Re-read its fence before accepting an idempotent retry.
        if existing.get("historicalAnonymousId") == player_id:
            latest = await anonymous_saves.find_one({"playerId": player_id})
            if (latest is not None and latest.get("claimedBy") == authenticated_user_id
                    and latest.get("revision") == expected_anonymous_revision):
                return deepcopy(existing)
        raise StoryClaimConflict("account already has a save; explicit choice required")

    result = await anonymous_saves.update_one(
        {"playerId": player_id, "revision": expected_anonymous_revision,
         "$or": [{"claimedBy": {"$exists": False}}, {"claimedBy": authenticated_user_id}]},
        {"$set": {"claimedBy": authenticated_user_id, "updatedAt": now}},
    )
    if result.matched_count != 1:
        raise StoryClaimConflict("anonymous save changed or was claimed")

    doc = {"userId": authenticated_user_id, "historicalAnonymousId": player_id,
           "saveSchemaVersion": anon["saveSchemaVersion"],
           "contentVersions": deepcopy(anon.get("contentVersions", {})),
           "playerState": story, "revision": 1, "createdAt": now, "updatedAt": now}
    try:
        inserted = await account_saves.insert_one(deepcopy(doc))
    except DuplicateKeyError:
        winner = await account_saves.find_one({"userId": authenticated_user_id})
        if winner is not None and winner.get("historicalAnonymousId") == player_id:
            return deepcopy(winner)
        raise StoryClaimConflict("concurrent account save won; review required")
    doc["_id"] = inserted.inserted_id
    return deepcopy(doc)
