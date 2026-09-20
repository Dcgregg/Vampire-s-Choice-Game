"""Authenticated account-progression bootstrap route; not registered live."""
from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from .account_progression_bootstrap import AccountProgressionUnavailable
from .csrf import require_trusted_progression_header
from .rate_limit import AccountRateLimiter


_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def make_account_progression_router(
    *, current_user: Callable[..., Awaitable[dict]],
    bootstrap: Callable[..., Awaitable[dict]],
    rate_limiter: AccountRateLimiter | None = None,
) -> APIRouter:
    """Build an opt-in mutating bootstrap endpoint with no client state input."""
    router = APIRouter(prefix="/api")

    @router.post("/me/progression/bootstrap")
    async def bootstrap_progression(
        request: Request,
        response: Response,
        user: dict = Depends(current_user),
    ):
        response.headers.update(_NO_STORE)
        require_trusted_progression_header(request)
        if rate_limiter is not None:
            rate_limiter.require(user["user_id"])
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
