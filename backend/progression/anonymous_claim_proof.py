"""Inert primitives for future anonymous-save claim credentials.

Not registered with the live anonymous save endpoints. A credential must be
issued only on an authenticated-to-the-anonymous-device creation path and
stored as a hash on the save. Never expose the digest as a bearer credential.
Existing saves have no credential and MUST NOT be silently backfilled based
solely on knowledge of playerId or revision.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any, Mapping


class InvalidClaimProof(ValueError):
    """Missing, malformed or mismatched proof; do not reveal which."""


# 32 random bytes, URL-safe base64 without padding (43 characters).
_CREDENTIAL_BYTES = 32
_CREDENTIAL_LENGTH = 43
_DOMAIN = b"vampires-choice:anonymous-claim:v1:\x00"


def issue_claim_credential() -> tuple[str, str]:
    """Return (one-time-visible bearer credential, stored SHA-256 digest)."""
    credential = secrets.token_urlsafe(_CREDENTIAL_BYTES)
    return credential, credential_digest(credential)


def credential_digest(credential: str) -> str:
    """Hash a well-formed credential with domain separation."""
    if (not isinstance(credential, str) or len(credential) != _CREDENTIAL_LENGTH
            or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-' for c in credential)):
        raise InvalidClaimProof('invalid claim proof')
    return hashlib.sha256(_DOMAIN + credential.encode('ascii')).hexdigest()


def verify_claim_credential(save: Mapping[str, Any], credential: str) -> bool:
    """Fail closed for legacy saves and malformed proofs; compare digests safely."""
    stored = save.get('claimCredentialDigest') if isinstance(save, Mapping) else None
    if (not isinstance(stored, str) or len(stored) != 64
            or any(c not in '0123456789abcdef' for c in stored)):
        return False
    try:
        presented = credential_digest(credential)
    except InvalidClaimProof:
        return False
    return hmac.compare_digest(stored, presented)
