"""Opt-in, transactional story-only claim; NOT wired to the live API.

The caller must resolve the account ID from a verified server session. Both
collections must belong to the same MongoDB deployment supporting transactions.
This module never imports client rewards into trusted progression.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from pymongo.errors import DuplicateKeyError, OperationFailure

from .story_only_transfer import story_only_player_state


class StoryClaimConflict(ValueError):
    """Claim needs explicit resolution, or another writer won the race."""


class StoryClaimDenied(ValueError):
    """Anonymous save is missing or belongs to another account."""


async def claim_story_only(
    anonymous_saves: Any, account_saves: Any, *, authenticated_user_id: str,
    player_id: str, expected_anonymous_revision: int, now: str,
) -> dict:
    """Atomically claim a server-stored anonymous save into a NEW account save.

    Requires unique indexes on playerId and userId. Never overwrites an existing
    account save. MongoDB aborts both writes if either fails. This is a building
    block, not an API handler or reward writer.
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
    if anonymous_saves.database.client is not account_saves.database.client:
        raise StoryClaimConflict("claim collections must share one MongoDB client")

    try:
        async with await anonymous_saves.database.client.start_session() as session:
            async with session.start_transaction():
                anon = await anonymous_saves.find_one({"playerId": player_id}, session=session)
                if anon is None:
                    raise StoryClaimDenied("anonymous save not found")
                if anon.get("claimedBy") not in (None, authenticated_user_id):
                    raise StoryClaimDenied("anonymous save belongs to another account")
                if anon.get("revision") != expected_anonymous_revision:
                    raise StoryClaimConflict("anonymous save revision changed")
                story = story_only_player_state(anon.get("playerState"))
                existing = await account_saves.find_one(
                    {"userId": authenticated_user_id}, session=session)
                if existing is not None:
                    if (existing.get("historicalAnonymousId") == player_id
                            and anon.get("claimedBy") == authenticated_user_id):
                        return deepcopy(existing)
                    raise StoryClaimConflict("account already has a save; explicit choice required")
                result = await anonymous_saves.update_one(
                    {"playerId": player_id, "revision": expected_anonymous_revision,
                     "$or": [{"claimedBy": {"$exists": False}},
                             {"claimedBy": authenticated_user_id}]},
                    {"$set": {"claimedBy": authenticated_user_id, "updatedAt": now}},
                    session=session,
                )
                if result.matched_count != 1:
                    raise StoryClaimConflict("anonymous save changed or was claimed")
                doc = {"userId": authenticated_user_id,
                       "historicalAnonymousId": player_id,
                       "saveSchemaVersion": anon["saveSchemaVersion"],
                       "contentVersions": deepcopy(anon.get("contentVersions", {})),
                       "playerState": story, "revision": 1,
                       "createdAt": now, "updatedAt": now}
                inserted = await account_saves.insert_one(deepcopy(doc), session=session)
                doc["_id"] = inserted.inserted_id
                return deepcopy(doc)
    except DuplicateKeyError as exc:
        # A unique-index collision aborts the transaction, including its fence.
        # The caller can retry to read the winner, but cannot overwrite it.
        raise StoryClaimConflict("concurrent account save won; review or retry") from exc
    except OperationFailure as exc:
        if exc.has_error_label("TransientTransactionError"):
            raise StoryClaimConflict("concurrent claim changed; retry") from exc
        raise
