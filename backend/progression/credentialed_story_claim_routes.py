"""Opt-in credentialed story claim route; never registered in the live server.

The anonymous credential is a bearer secret supplied in a request header, never
in the URL or response. Do not log request headers in any eventual deployment.
The claim service checks the proof inside the same MongoDB transaction as the
ownership fence. This module does not authenticate or issue the credential.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .credentialed_story_claim import claim_story_with_credential
from .story_claim import StoryClaimConflict, StoryClaimDenied


class CredentialedClaimRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    playerId: str = Field(pattern=r'^vc_[A-Za-z0-9_-]{8,64}$')
    expectedAnonymousRevision: int = Field(ge=1, strict=True)


def make_credentialed_story_claim_router(
    anonymous_saves: Any, account_saves: Any, *,
    current_user: Callable[..., Awaitable[dict]], now: Callable[[], str],
) -> APIRouter:
    """Build an unregistered router; verified identity is a required dependency."""
    router = APIRouter(prefix='/api')

    @router.post('/me/claim-story-with-credential')
    async def claim(
        body: CredentialedClaimRequest,
        user: dict = Depends(current_user),
        credential: str | None = Header(default=None, alias='X-Anonymous-Claim-Credential'),
    ):
        if credential is None:
            raise HTTPException(status_code=403, detail={'error': 'claim_denied'})
        try:
            doc = await claim_story_with_credential(
                anonymous_saves, account_saves,
                authenticated_user_id=user['user_id'],
                player_id=body.playerId,
                expected_anonymous_revision=body.expectedAnonymousRevision,
                claim_credential=credential,
                now=now(),
            )
        except StoryClaimDenied as exc:
            raise HTTPException(status_code=403, detail={'error': 'claim_denied'}) from exc
        except StoryClaimConflict as exc:
            raise HTTPException(status_code=409, detail={
                'error': 'claim_conflict',
                'resolution': 'review_existing_progress_or_retry',
            }) from exc
        return {
            'saveSchemaVersion': doc['saveSchemaVersion'],
            'contentVersions': doc.get('contentVersions', {}),
            'playerState': doc['playerState'],
            'revision': doc['revision'],
            'createdAt': doc['createdAt'],
            'updatedAt': doc['updatedAt'],
        }

    return router
