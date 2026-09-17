"""Inert creation primitive for NEW anonymous saves; not registered in server.py.

The caller supplies server-owned initial narrative data, never a client-chosen
player ID. The credential is returned only after the insert succeeds. This
cannot retrofit legacy saves or authenticate existing anonymous PUT/GET routes.
"""
from __future__ import annotations

import secrets
from copy import deepcopy
from typing import Any, Mapping

from pymongo.errors import DuplicateKeyError

from .anonymous_claim_proof import issue_claim_credential


class AnonymousCreationUnavailable(RuntimeError):
    """No anonymous identity was issued; caller must retry creation."""


def _validate_initial_save(initial_save: Mapping[str, Any], now: str) -> None:
    """Fail closed if a future server factory accidentally supplies bad state."""
    if not isinstance(initial_save, Mapping) or not isinstance(now, str) or not now:
        raise ValueError('validated initial save and timestamp required')
    version = initial_save.get('saveSchemaVersion')
    content_versions = initial_save.get('contentVersions')
    state = initial_save.get('playerState')
    if (type(version) is not int or version < 1
            or not isinstance(content_versions, Mapping)
            or any(not isinstance(key, str) or type(value) is not int or value < 1
                   for key, value in content_versions.items())
            or not isinstance(state, Mapping)):
        raise ValueError('invalid initial save envelope')
    # A newly issued identity cannot start with client- or factory-provided
    # rewards. Trusted account grants are a separate, server-owned operation.
    if (state.get('bloodCoins', 0) != 0 or state.get('achievements', {}) != {}
            or state.get('dailyStreak', 0) != 0):
        raise ValueError('initial anonymous save must not contain rewards')


async def create_credentialed_anonymous_save(
    anonymous_saves: Any, *, initial_save: Mapping[str, Any], now: str,
) -> tuple[dict, str]:
    """Insert a fresh server-generated ID and digest; return (public save, secret).

    Requires a unique playerId index. Never returns a credential on a failed
    insert, and never accepts an existing ID or credential from initial_save.
    """
    _validate_initial_save(initial_save, now)
    for _ in range(3):
        player_id = 'vc_' + secrets.token_urlsafe(24)
        credential, digest = issue_claim_credential()
        doc = {
            'playerId': player_id,
            'claimCredentialDigest': digest,
            'saveSchemaVersion': deepcopy(initial_save['saveSchemaVersion']),
            'contentVersions': deepcopy(dict(initial_save['contentVersions'])),
            'playerState': deepcopy(dict(initial_save['playerState'])),
            'revision': 1,
            'createdAt': now,
            'updatedAt': now,
        }
        try:
            await anonymous_saves.insert_one(doc)
        except DuplicateKeyError:
            continue
        # Never expose Mongo _id or the credential digest in the public save.
        public = {key: deepcopy(value) for key, value in doc.items()
                  if key not in ('_id', 'claimCredentialDigest')}
        return public, credential
    raise AnonymousCreationUnavailable('anonymous creation unavailable')
