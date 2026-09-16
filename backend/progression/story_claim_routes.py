"""Opt-in story-only claim API router; deliberately NOT registered in server.py.

Registration requires an explicit cutover review of the existing /api/me/claim
flow and frontend conflict UX. This router never writes authoritative rewards.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .story_claim import StoryClaimConflict, StoryClaimDenied, claim_story_only


class StoryClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    playerId: str = Field(pattern=r"^vc_[A-Za-z0-9_-]{8,64}$")
    expectedAnonymousRevision: int = Field(ge=1, strict=True)


def make_story_claim_router(
    anonymous_saves: Any,
    account_saves: Any,
    *,
    current_user: Callable[..., Awaitable[dict]],
    now: Callable[[], str],
) -> APIRouter:
    """Build a route whose account identity comes solely from server auth."""
    router = APIRouter(prefix="/api")

    @router.post("/me/claim-story-only")
    async def claim(body: StoryClaimRequest, user: dict = Depends(current_user)):
        try:
            doc = await claim_story_only(
                anonymous_saves, account_saves,
                authenticated_user_id=user["user_id"],
                player_id=body.playerId,
                expected_anonymous_revision=body.expectedAnonymousRevision,
                now=now(),
            )
        except StoryClaimDenied as exc:
            # Do not reveal another account's identity or save contents.
            raise HTTPException(status_code=403, detail={"error": "claim_denied"}) from exc
        except StoryClaimConflict as exc:
            raise HTTPException(status_code=409, detail={
                "error": "claim_conflict", "reason": str(exc),
                "resolution": "review_existing_progress_or_retry",
            }) from exc
        return {
            "saveSchemaVersion": doc["saveSchemaVersion"],
            "contentVersions": doc.get("contentVersions", {}),
            "playerState": doc["playerState"],
            "revision": doc["revision"],
            "createdAt": doc["createdAt"],
            "updatedAt": doc["updatedAt"],
        }

    return router
