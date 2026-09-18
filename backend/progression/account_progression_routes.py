"""Authenticated account-progression bootstrap route; not registered live."""
from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, Response

from .account_progression_bootstrap import AccountProgressionUnavailable


_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def make_account_progression_router(
    *, current_user: Callable[..., Awaitable[dict]],
    bootstrap: Callable[..., Awaitable[dict]],
) -> APIRouter:
    """Build an opt-in mutating bootstrap endpoint with no client state input."""
    router = APIRouter(prefix="/api")

    @router.post("/me/progression/bootstrap")
    async def bootstrap_progression(
        response: Response,
        user: dict = Depends(current_user),
    ):
        response.headers.update(_NO_STORE)
        try:
            ledger = await bootstrap(authenticated_user_id=user["user_id"])
        except AccountProgressionUnavailable as exc:
            raise HTTPException(
                status_code=503,
                detail={"error": "progression_bootstrap_unavailable",
                        "retryable": False},
                headers=_NO_STORE,
            ) from exc
        return {"ledger": ledger}

    return router
