"""Strict authenticated progression route factory; not registered live."""
from __future__ import annotations

import logging
from typing import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from .strict_event_input import StrictChoiceEvent, StrictLifecycleEvent
from .csrf import require_trusted_progression_header
from .rate_limit import AccountRateLimiter
from .trusted_choice_service import (
    TrustedChoiceConflict, TrustedChoiceIndeterminate, TrustedChoiceUnavailable,
    TrustedChoiceValidationError,
)


_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}
logger = logging.getLogger("trusted_progression")


def _log_rejection(kind: str, status: str) -> None:
    logger.warning(
        "trusted_progression_outcome",
        extra={"progression_kind": kind, "progression_status": status},
    )


def make_trusted_progression_router(
    *, current_user: Callable[..., Awaitable[dict]],
    process_choice: Callable[..., Awaitable[dict]],
    process_lifecycle: Callable[..., Awaitable[dict]] | None = None,
    rate_limiter: AccountRateLimiter | None = None,
) -> APIRouter:
    """Build an opt-in router without registering or enabling it."""
    router = APIRouter(prefix="/api")

    @router.post("/me/progression/choices")
    async def submit_choice(
        body: StrictChoiceEvent,
        request: Request,
        response: Response,
        user: dict = Depends(current_user),
    ):
        response.headers.update(_NO_STORE)
        require_trusted_progression_header(request)
        if rate_limiter is not None:
            rate_limiter.require(user["user_id"])
        try:
            return await process_choice(
                authenticated_user_id=user["user_id"], event=body,
            )
        except TrustedChoiceUnavailable as exc:
            _log_rejection("choice", "unavailable")
            raise HTTPException(
                status_code=404, detail={"error": "progression_unavailable"},
                headers=_NO_STORE,
            ) from exc
        except TrustedChoiceValidationError as exc:
            _log_rejection("choice", "invalid")
            raise HTTPException(
                status_code=422, detail={"error": "invalid_choice"},
                headers=_NO_STORE,
            ) from exc
        except TrustedChoiceConflict as exc:
            _log_rejection("choice", "conflict")
            raise HTTPException(
                status_code=409, detail={"error": "progression_conflict",
                                         "action": "refresh_and_retry"},
                headers=_NO_STORE,
            ) from exc
        except TrustedChoiceIndeterminate as exc:
            _log_rejection("choice", "indeterminate")
            raise HTTPException(
                status_code=503, detail={"error": "progression_indeterminate",
                                         "retryable": True},
                headers=_NO_STORE,
            ) from exc

    if process_lifecycle is not None:
        @router.post("/me/progression/lifecycle")
        async def submit_lifecycle(
            body: StrictLifecycleEvent,
            request: Request,
            response: Response,
            user: dict = Depends(current_user),
        ):
            response.headers.update(_NO_STORE)
            require_trusted_progression_header(request)
            if rate_limiter is not None:
                rate_limiter.require(user["user_id"])
            try:
                return await process_lifecycle(
                    authenticated_user_id=user["user_id"], event=body,
                )
            except TrustedChoiceUnavailable as exc:
                _log_rejection("lifecycle", "unavailable")
                raise HTTPException(
                    status_code=404, detail={"error": "progression_unavailable"},
                    headers=_NO_STORE,
                ) from exc
            except TrustedChoiceValidationError as exc:
                _log_rejection("lifecycle", "invalid")
                raise HTTPException(
                    status_code=422, detail={"error": "invalid_lifecycle"},
                    headers=_NO_STORE,
                ) from exc
            except TrustedChoiceConflict as exc:
                _log_rejection("lifecycle", "conflict")
                raise HTTPException(
                    status_code=409, detail={"error": "progression_conflict",
                                             "action": "refresh_and_retry"},
                    headers=_NO_STORE,
                ) from exc
            except TrustedChoiceIndeterminate as exc:
                _log_rejection("lifecycle", "indeterminate")
                raise HTTPException(
                    status_code=503, detail={"error": "progression_indeterminate",
                                             "retryable": True},
                    headers=_NO_STORE,
                ) from exc

    return router
