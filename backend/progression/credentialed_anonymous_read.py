"""Opt-in anonymous read primitive; NOT wired to legacy or live routes.

A player ID is a locator, never proof of ownership. Return only a public
narrative envelope after checking the current bearer credential. Do not log
credentials, cache responses, or expose the stored digest.
"""
from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .anonymous_claim_proof import verify_claim_credential


_PLAYER_ID = re.compile(r'vc_[A-Za-z0-9_-]{8,64}\Z')


class AnonymousReadDenied(Exception):
    """Uniform denial for missing, malformed, legacy or mismatched proof."""


async def read_credentialed_anonymous_save(
    anonymous_saves: Any, *, player_id: str, claim_credential: str,
) -> dict:
    """Read an unclaimed save only after verifying its current bearer proof."""
    if not isinstance(player_id, str) or _PLAYER_ID.fullmatch(player_id) is None:
        raise AnonymousReadDenied('anonymous read denied')
    doc = await anonymous_saves.find_one({'playerId': player_id})
    if (doc is None or doc.get('claimedBy') is not None
            or not verify_claim_credential(doc, claim_credential)):
        raise AnonymousReadDenied('anonymous read denied')
    return {key: deepcopy(doc[key]) for key in (
        'playerId', 'saveSchemaVersion', 'contentVersions', 'playerState',
        'revision', 'createdAt', 'updatedAt',
    )}
