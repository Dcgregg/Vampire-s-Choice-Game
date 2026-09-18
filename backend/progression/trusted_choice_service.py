"""Authenticated trusted-progression orchestrator; inert until registered.

The caller must resolve ``authenticated_user_id`` from a verified server
session. This service never accepts a browser ledger ID, owner ID, projection,
award or balance. Choice, achievement, lifecycle and terminal changes are
derived from the pinned trusted registry and committed as one projection.
"""
from __future__ import annotations

import logging
from time import time_ns
from typing import Any, Mapping

from .attributed_mongo_reservations import AttributedMongoReservationStore
from .attribution import AttributionUnproven, require_event_attribution
from .canonical_event import canonical_event_sha256
from .choice_checkpoint_guard import CheckpointConflict
from .mongo_reservations import (
    ProgressionConflict, ReservationBusy, ReservationInvariantError,
)
from .strict_event_input import StrictChoiceEvent, StrictLifecycleEvent
from .trusted_choice_reservation import (
    plan_account_choice_reservation, plan_account_lifecycle_reservation,
)
from .trusted_content import InvalidChoice, UnknownContentVersion
from .trusted_owner import ProgressionAccessDenied, require_account_ledger_owner

logger = logging.getLogger("trusted_progression")


def _public_result(status: str, event: Any, ledger: Mapping[str, Any]) -> dict:
    logger.info(
        "trusted_progression_outcome",
        extra={"progression_kind": event.kind, "progression_status": status},
    )
    return {"status": status, "eventId": event.eventId,
            "ledger": public_account_ledger(ledger)}


class TrustedChoiceUnavailable(Exception):
    """No authenticated, account-owned trusted ledger is available."""


class TrustedChoiceValidationError(Exception):
    """The strictly parsed event is unsupported or invalid for trusted content."""


class TrustedChoiceConflict(Exception):
    """The event conflicts with durable revision, checkpoint or prior intent."""


class TrustedChoiceIndeterminate(Exception):
    """Durable state must be reconciled before the client may claim success."""


def public_account_ledger(ledger: Mapping[str, Any]) -> dict:
    """Return only the authoritative fields safe for the authenticated client."""
    checkpoint = ledger.get("checkpoint")
    coins = ledger.get("coins")
    achievements = ledger.get("achievements")
    revision = ledger.get("progressionRevision")
    confirmed = coins.get("confirmed") if isinstance(coins, Mapping) else None
    if (ledger.get("ownerType") != "account" or not isinstance(checkpoint, Mapping)
            or type(checkpoint.get("bookId")) is not str
            or type(checkpoint.get("contentVersion")) is not int
            or type(checkpoint.get("currentSceneId")) is not str
            or type(checkpoint.get("terminal")) is not bool
            or not isinstance(coins, Mapping) or type(confirmed) is not int
            or confirmed < 0 or not isinstance(achievements, Mapping)
            or type(revision) is not int or revision < 0):
        raise TrustedChoiceIndeterminate("authoritative ledger is malformed")
    return {
        "ownerType": "account",
        "coins": {"confirmed": confirmed},
        "achievements": dict(achievements),
        "checkpoint": {
            "bookId": checkpoint.get("bookId"),
            "contentVersion": checkpoint.get("contentVersion"),
            "currentSceneId": checkpoint.get("currentSceneId"),
            "terminal": checkpoint.get("terminal"),
        },
        "progressionRevision": revision,
    }


async def _owned_ledger(ledgers: Any, owner_id: str) -> dict:
    ledger = await ledgers.find_one({"ownerType": "account", "ownerId": owner_id})
    try:
        return require_account_ledger_owner(
            ledger, authenticated_user_id=owner_id,
        )
    except ProgressionAccessDenied as exc:
        raise TrustedChoiceUnavailable("trusted progression unavailable") from exc


async def _process_account_event(
    ledgers: Any, events: Any, registry: Mapping[str, Any], *,
    authenticated_user_id: str, event: StrictChoiceEvent | StrictLifecycleEvent,
    opening_book_id: str | None = None, opening_content_version: int | None = None,
    opening_scene_id: str | None = None,
) -> dict:
    """Validate, reserve, commit and reconcile one account-owned event."""
    ledger = await _owned_ledger(ledgers, authenticated_user_id)
    payload_hash = canonical_event_sha256(event.model_dump(mode="python"))
    existing = await events.find_one({"ledgerId": ledger["_id"],
                                      "eventId": event.eventId})
    store = AttributedMongoReservationStore(ledgers, events)

    if existing is not None:
        if existing.get("payloadHash") != payload_hash:
            raise TrustedChoiceConflict("event ID already has different intent")
        if (existing.get("expectedOwnerType") != "account"
                or existing.get("expectedOwnerId") != authenticated_user_id):
            raise TrustedChoiceUnavailable("trusted progression unavailable")
        if existing.get("status") == "applied":
            try:
                require_event_attribution(ledger, existing)
            except AttributionUnproven as exc:
                raise TrustedChoiceIndeterminate("applied event lacks durable attribution") from exc
            return _public_result("duplicate", event, ledger)
        if existing.get("status") == "committing":
            try:
                await store.recover(existing)
            except ReservationBusy as exc:
                raise TrustedChoiceIndeterminate("event is still being reconciled") from exc
            except (AttributionUnproven, ProgressionConflict,
                    ReservationInvariantError) as exc:
                raise TrustedChoiceIndeterminate("event reconciliation failed closed") from exc
            confirmed = await _owned_ledger(ledgers, authenticated_user_id)
            return _public_result("duplicate", event, confirmed)

    try:
        unlocked_at = time_ns() // 1_000_000
        if isinstance(event, StrictChoiceEvent):
            plan = plan_account_choice_reservation(
                registry, ledger, event,
                authenticated_user_id=authenticated_user_id,
                unlocked_at=unlocked_at,
            )
        elif (isinstance(event, StrictLifecycleEvent)
                and opening_book_id is not None
                and opening_content_version is not None
                and opening_scene_id is not None):
            plan = plan_account_lifecycle_reservation(
                registry, ledger, event,
                authenticated_user_id=authenticated_user_id,
                unlocked_at=unlocked_at,
                opening_book_id=opening_book_id,
                opening_content_version=opening_content_version,
                opening_scene_id=opening_scene_id,
            )
        else:
            raise TrustedChoiceValidationError("unsupported trusted progression event")
        reserved = await store.reserve(**plan)
        if reserved.get("status") == "applied":
            require_event_attribution(ledger, reserved)
            return _public_result("duplicate", event, ledger)
        await store.commit(event=reserved, lease_owner=reserved["leaseOwner"])
        await store.finalise(event=reserved, payload_hash=payload_hash)
    except (InvalidChoice, UnknownContentVersion) as exc:
        raise TrustedChoiceValidationError("choice is not valid trusted content") from exc
    except CheckpointConflict as exc:
        raise TrustedChoiceConflict("choice does not match authoritative progress") from exc
    except ProgressionConflict as exc:
        raise TrustedChoiceConflict("authoritative progress changed") from exc
    except ReservationInvariantError as exc:
        raise TrustedChoiceConflict("event ID conflicts with durable intent") from exc
    except (ReservationBusy, AttributionUnproven) as exc:
        raise TrustedChoiceIndeterminate("choice outcome requires reconciliation") from exc

    confirmed = await _owned_ledger(ledgers, authenticated_user_id)
    return _public_result("confirmed", event, confirmed)


async def process_account_choice(
    ledgers: Any, events: Any, registry: Mapping[str, Any], *,
    authenticated_user_id: str, event: StrictChoiceEvent,
) -> dict:
    if not isinstance(event, StrictChoiceEvent):
        raise TrustedChoiceValidationError("choice event required")
    return await _process_account_event(
        ledgers, events, registry,
        authenticated_user_id=authenticated_user_id, event=event,
    )


async def process_account_lifecycle(
    ledgers: Any, events: Any, registry: Mapping[str, Any], *,
    authenticated_user_id: str, event: StrictLifecycleEvent,
    opening_book_id: str, opening_content_version: int, opening_scene_id: str,
) -> dict:
    if not isinstance(event, StrictLifecycleEvent):
        raise TrustedChoiceValidationError("lifecycle event required")
    return await _process_account_event(
        ledgers, events, registry,
        authenticated_user_id=authenticated_user_id, event=event,
        opening_book_id=opening_book_id,
        opening_content_version=opening_content_version,
        opening_scene_id=opening_scene_id,
    )
