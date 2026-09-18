"""Opt-in story-only claim API router; deliberately NOT registered in server.py.

Registration requires a server-verifiable anonymous ownership credential and
an explicit cutover review. This router never writes authoritative rewards.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

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
    verify_ownership: Optional[Callable[[str, str], Awaitable[bool]]] = None,
) -> APIRouter:
    """Build an isolated route; missing ownership verification denies all claims.

    The verifier must check server-issued proof from the request's authenticated
    browser context, not playerId or revision alone. Its implementation and
    issuance lifecycle are intentionally not supplied by this prototype.
    """
    router = APIRouter(prefix="/api")

    @router.post("/me/claim-story-only")
    async def claim(body: StoryClaimRequest, user: dict = Depends(current_user)):
        # Fail closed: no verifier means no claim, even for a valid session.
        # Do not expose proof in JSON, URLs, logs, or exception messages.
        if verify_ownership is None:
            raise HTTPException(status_code=403, detail={"error": "claim_denied"})
        try:
            verified = await verify_ownership(body.playerId, user["user_id"])
        except Exception:
            verified = False
        if verified is not True:
            raise HTTPException(status_code=403, detail={"error": "claim_denied"})
        try:
            doc = await claim_story_only(
                anonymous_saves, account_saves,
                authenticated_user_id=user["user_id"],
                player_id=body.playerId,
                expected_anonymous_revision=body.expectedAnonymousRevision,
                now=now(),
            )
        except StoryClaimDenied as exc:
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
