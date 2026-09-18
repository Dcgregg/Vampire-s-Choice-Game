"""Fail-closed composition for the authenticated trusted-progression routes.

The routes and their startup index writes remain absent unless the deployment
sets the exact activation token. Keeping the parser here makes accidental
truthy strings such as ``true`` or ``1`` insufficient to activate the feature.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Mapping

from fastapi import FastAPI

from .account_progression_bootstrap import bootstrap_account_progression
from .account_progression_routes import make_account_progression_router
from .attributed_mongo_reservations import AttributedMongoReservationStore
from .trusted_choice_service import process_account_choice, process_account_lifecycle
from .trusted_progression_routes import make_trusted_progression_router
from .rate_limit import AccountRateLimiter


TRUSTED_PROGRESSION_ENV = "TRUSTED_PROGRESSION_ROUTES"
TRUSTED_PROGRESSION_ACTIVATION_TOKEN = "enabled"
OPENING_BOOK_ID = "book1"
OPENING_CONTENT_VERSION = 1
OPENING_SCENE_ID = "b1_c1_s1"


def trusted_progression_routes_enabled(value: str | None) -> bool:
    """Enable only for the exact reviewed token; every other value is off."""
    return value == TRUSTED_PROGRESSION_ACTIVATION_TOKEN


def register_trusted_progression_routes(
    app: FastAPI,
    *,
    activation_value: str | None,
    current_user: Callable[..., Awaitable[dict]],
    ledgers: Any,
    events: Any,
    registry: Mapping[str, Any] | None,
) -> bool:
    """Register bootstrap and choice routes only after explicit activation."""
    if not trusted_progression_routes_enabled(activation_value):
        return False
    if registry is None:
        raise RuntimeError("trusted progression registry required when enabled")

    async def bootstrap(*, authenticated_user_id: str) -> dict:
        return await bootstrap_account_progression(
            ledgers,
            registry,
            authenticated_user_id=authenticated_user_id,
            book_id=OPENING_BOOK_ID,
            content_version=OPENING_CONTENT_VERSION,
            scene_id=OPENING_SCENE_ID,
        )

    async def process_choice(*, authenticated_user_id: str, event: Any) -> dict:
        return await process_account_choice(
            ledgers,
            events,
            registry,
            authenticated_user_id=authenticated_user_id,
            event=event,
        )

    async def process_lifecycle(*, authenticated_user_id: str, event: Any) -> dict:
        return await process_account_lifecycle(
            ledgers,
            events,
            registry,
            authenticated_user_id=authenticated_user_id,
            event=event,
            opening_book_id=OPENING_BOOK_ID,
            opening_content_version=OPENING_CONTENT_VERSION,
            opening_scene_id=OPENING_SCENE_ID,
        )

    rate_limiter = AccountRateLimiter()

    app.include_router(make_account_progression_router(
        current_user=current_user,
        bootstrap=bootstrap,
        rate_limiter=rate_limiter,
    ))
    app.include_router(make_trusted_progression_router(
        current_user=current_user,
        process_choice=process_choice,
        process_lifecycle=process_lifecycle,
        rate_limiter=rate_limiter,
    ))
    return True


async def ensure_trusted_progression_indexes(
    *, activation_value: str | None, ledgers: Any, events: Any,
) -> bool:
    """Create progression indexes only for an explicitly enabled deployment."""
    if not trusted_progression_routes_enabled(activation_value):
        return False
    await AttributedMongoReservationStore(ledgers, events).ensure_indexes()
    return True
