"""Prepare an untrusted save for story-only account linking.

Inert Phase 6B helper. This does NOT authenticate the caller, verify ownership,
validate story choices, or activate a migration route. It intentionally preserves
the existing save envelope for the legacy reader while resetting all reward-like
client fields. The authoritative ledger must be created separately by the server.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


class InvalidStoryTransfer(ValueError):
    pass


# Explicit allowlist: unknown client fields cannot smuggle a second balance,
# entitlement or achievement into the account save.
STORY_FIELDS = ("player", "relationships", "flags", "progress", "settings", "version")


def story_only_player_state(source: Mapping[str, Any]) -> dict:
    """Copy narrative state, discarding client rewards and login-derived grants.

    This is a compatibility shape for the existing playerState reader, not a
    source of trusted progression or proof that any narrative claim is genuine.
    """
    if not isinstance(source, Mapping):
        raise InvalidStoryTransfer("playerState must be an object")
    if not isinstance(source.get("progress"), Mapping):
        raise InvalidStoryTransfer("story progress is required")
    for field in ("relationships", "flags", "settings"):
        if not isinstance(source.get(field), Mapping):
            raise InvalidStoryTransfer(f"{field} must be an object")
    if not isinstance(source.get("version"), int) or isinstance(source["version"], bool):
        raise InvalidStoryTransfer("state version must be an integer")
    state = {field: deepcopy(source[field]) for field in STORY_FIELDS if field in source}
    # The legacy reader expects these fields; none are an authoritative award.
    state.update(bloodCoins=0, achievements={}, dailyStreak=0, lastLoginDate="")
    return state
