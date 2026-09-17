"""Inert credential-gated anonymous write; never register with legacy routes.

The bearer proof is a header in a future HTTP adapter, never a URL parameter.
This helper accepts only narrative fields and never treats client rewards as
trusted. A claim or credential rotation racing the write fails its CAS filter.
"""
from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Mapping

from .anonymous_claim_proof import verify_claim_credential
from .story_only_transfer import InvalidStoryTransfer, story_only_player_state


_PLAYER_ID = re.compile(r'vc_[A-Za-z0-9_-]{8,64}\Z')


class AnonymousWriteDenied(Exception):
    """Missing, malformed, legacy, claimed or incorrect proof."""


class AnonymousWriteConflict(Exception):
    """Stale revision or concurrent change; caller must reload."""


async def write_credentialed_anonymous_save(
    anonymous_saves: Any, *, player_id: str, claim_credential: str,
    expected_revision: int, player_state: Mapping[str, Any], now: str,
) -> dict:
    """CAS-update an unclaimed save's story without accepting reward fields."""
    if (not isinstance(player_id, str) or _PLAYER_ID.fullmatch(player_id) is None
            or not isinstance(now, str) or not now):
        raise AnonymousWriteDenied('anonymous write denied')
    if type(expected_revision) is not int or expected_revision < 1:
        raise AnonymousWriteConflict('invalid anonymous revision')
    try:
        story = story_only_player_state(player_state)
    except InvalidStoryTransfer as exc:
        raise AnonymousWriteConflict('invalid narrative state') from exc
    doc = await anonymous_saves.find_one({'playerId': player_id})
    if (doc is None or doc.get('claimedBy') is not None
            or not verify_claim_credential(doc, claim_credential)):
        raise AnonymousWriteDenied('anonymous write denied')
    if doc.get('revision') != expected_revision:
        raise AnonymousWriteConflict('anonymous revision changed')
    result = await anonymous_saves.update_one(
        {'playerId': player_id, 'revision': expected_revision,
         'claimCredentialDigest': doc['claimCredentialDigest'],
         '$or': [{'claimedBy': {'$exists': False}}, {'claimedBy': None}]},
        {'$set': {'playerState': story, 'updatedAt': now}, '$inc': {'revision': 1}},
    )
    if result.matched_count != 1:
        raise AnonymousWriteConflict('anonymous save changed')
    return {'playerId': player_id, 'saveSchemaVersion': deepcopy(doc['saveSchemaVersion']),
            'contentVersions': deepcopy(doc['contentVersions']),
            'playerState': deepcopy(story), 'revision': expected_revision + 1,
            'createdAt': doc['createdAt'], 'updatedAt': now}
