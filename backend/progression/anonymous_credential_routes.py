"""Opt-in issuance route for NEW anonymous identities; never registered live.

The initial narrative envelope comes from a trusted server factory, not from a
browser payload. The bearer credential is returned exactly once, over HTTPS in
an eventual deployment. The caller must prevent response/header logging and
provide rate limiting, origin protections and recovery policy before activation.
This endpoint cannot grant ownership of any pre-existing anonymous save.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from fastapi import APIRouter, HTTPException, Response

from .anonymous_credential_issuance import (
    AnonymousCreationUnavailable, create_credentialed_anonymous_save,
)


def make_anonymous_credential_router(
    anonymous_saves: Any, *, initial_save: Callable[[], Mapping[str, Any]],
    now: Callable[[], str],
) -> APIRouter:
    """Construct an unregistered route; server owns initial state and player ID."""
    router = APIRouter(prefix='/api')

    @router.post('/anonymous/credentialed-save', status_code=201)
    async def create(response: Response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Pragma'] = 'no-cache'
        try:
            public, credential = await create_credentialed_anonymous_save(
                anonymous_saves, initial_save=initial_save(), now=now(),
            )
        except (AnonymousCreationUnavailable, ValueError) as exc:
            raise HTTPException(status_code=503, detail={'error': 'creation_unavailable'}) from exc
        return {'save': public, 'claimCredential': credential}

    return router
