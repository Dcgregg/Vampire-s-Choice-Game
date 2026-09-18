"""Strict authenticated progression route factory; not registered live."""
from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, Response

from .strict_event_input import StrictChoiceEvent
from .trusted_choice_service import (
    TrustedChoiceConflict, TrustedChoiceIndeterminate, TrustedChoiceUnavailable,
    TrustedChoiceValidationError,
)


_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def make_trusted_progression_router(
    *, current_user: Callable[..., Awaitable[dict]],
    process_choice: Callable[..., Awaitable[dict]],
) -> APIRouter:
    """Build an opt-in router without registering or enabling it."""
    router = APIRouter(prefix="/api")

    @router.post("/me/progression/choices")
    async def submit_choice(
        body: StrictChoiceEvent,
        response: Response,
        user: dict = Depends(current_user),
    ):
        response.headers.update(_NO_STORE)
        try:
            return await process_choice(
                authenticated_user_id=user["user_id"], event=body,
            )
        except TrustedChoiceUnavailable as exc:
            raise HTTPException(
                status_code=404, detail={"error": "progression_unavailable"},
                headers=_NO_STORE,
            ) from exc
        except TrustedChoiceValidationError as exc:
            raise HTTPException(
                status_code=422, detail={"error": "invalid_choice"},
                headers=_NO_STORE,
            ) from exc
        except TrustedChoiceConflict as exc:
            raise HTTPException(
                status_code=409, detail={"error": "progression_conflict",
                                         "action": "refresh_and_retry"},
                headers=_NO_STORE,
            ) from exc
        except TrustedChoiceIndeterminate as exc:
            raise HTTPException(
                status_code=503, detail={"error": "progression_indeterminate",
                                         "retryable": True},
                headers=_NO_STORE,
            ) from exc

    return router
