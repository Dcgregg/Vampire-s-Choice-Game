"""Credential-gated story claim, isolated from live routes.

Unlike the earlier claim prototype, this implementation verifies the presented
bearer proof against the anonymous document read *inside* the transaction.
Never pass credentials through URLs or log them. Legacy saves fail closed.
"""
from __future__ import annotations

import asyncio
import re
from copy import deepcopy
from typing import Any

from pymongo.errors import DuplicateKeyError, OperationFailure

from .anonymous_claim_proof import credential_digest, verify_claim_credential, InvalidClaimProof
from .story_claim import StoryClaimConflict, StoryClaimDenied
from .story_only_transfer import story_only_player_state


_ANONYMOUS_ID_PATTERN = re.compile(r'vc_[A-Za-z0-9_-]{8,64}\Z')


async def claim_story_with_credential(
    anonymous_saves: Any, account_saves: Any, *, authenticated_user_id: str,
    player_id: str, expected_anonymous_revision: int, claim_credential: str,
    now: str,
) -> dict:
    """Claim only when the credential matches the current transactional save.

    Requires unique indexes on playerId and userId and transaction-capable Mongo.
    A successful claim retains the digest on the claimed anonymous document;
    future account access must be controlled by authenticated account identity.
    """
    if not isinstance(authenticated_user_id, str) or not authenticated_user_id.strip():
        raise StoryClaimDenied('claim denied')
    if not isinstance(player_id, str) or _ANONYMOUS_ID_PATTERN.fullmatch(player_id) is None:
        raise StoryClaimDenied('claim denied')
    try:
        credential_digest(claim_credential)
    except InvalidClaimProof as exc:
        raise StoryClaimDenied('claim denied') from exc
    if (type(expected_anonymous_revision) is not int or expected_anonymous_revision < 1
            or not isinstance(now, str) or not now):
        raise StoryClaimConflict('invalid claim revision or timestamp')
    if anonymous_saves.database.client is not account_saves.database.client:
        raise StoryClaimConflict('claim collections must share one MongoDB client')

    for attempt in range(20):
        try:
            async with await anonymous_saves.database.client.start_session() as session:
                async with session.start_transaction():
                    anon = await anonymous_saves.find_one({'playerId': player_id}, session=session)
                    if anon is None or not verify_claim_credential(anon, claim_credential):
                        raise StoryClaimDenied('claim denied')
                    if anon.get('claimedBy') not in (None, authenticated_user_id):
                        raise StoryClaimDenied('claim denied')
                    if anon.get('revision') != expected_anonymous_revision:
                        raise StoryClaimConflict('anonymous save revision changed')
                    existing = await account_saves.find_one({'userId': authenticated_user_id}, session=session)
                    if existing is not None:
                        if (existing.get('historicalAnonymousId') == player_id
                                and anon.get('claimedBy') == authenticated_user_id):
                            return deepcopy(existing)
                        raise StoryClaimConflict('account already has a save; explicit choice required')
                    story = story_only_player_state(anon.get('playerState'))
                    result = await anonymous_saves.update_one(
                        {'playerId': player_id, 'revision': expected_anonymous_revision,
                         'claimCredentialDigest': anon['claimCredentialDigest'],
                         '$or': [{'claimedBy': None},
                                 {'claimedBy': authenticated_user_id}]},
                        {'$set': {'claimedBy': authenticated_user_id, 'updatedAt': now}},
                        session=session,
                    )
                    if result.matched_count != 1:
                        raise StoryClaimConflict('anonymous save changed or was claimed')
                    doc = {'userId': authenticated_user_id, 'historicalAnonymousId': player_id,
                           'saveSchemaVersion': anon['saveSchemaVersion'],
                           'contentVersions': deepcopy(anon.get('contentVersions', {})),
                           'playerState': story, 'revision': 1,
                           'createdAt': now, 'updatedAt': now}
                    inserted = await account_saves.insert_one(deepcopy(doc), session=session)
                    doc['_id'] = inserted.inserted_id
                    return deepcopy(doc)
        except DuplicateKeyError as exc:
            if attempt == 19:
                raise StoryClaimConflict('concurrent account save won; review required') from exc
        except OperationFailure as exc:
            if not exc.has_error_label('TransientTransactionError'):
                raise
            if attempt == 19:
                raise StoryClaimConflict('concurrent claim changed; retry later') from exc
        await asyncio.sleep(min(0.005 * (attempt + 1), 0.05))
    raise StoryClaimConflict('claim retry limit reached')
