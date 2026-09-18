"""Authenticated trusted-choice orchestrator; inert until a route is registered.

The caller must resolve ``authenticated_user_id`` from a verified server
session. This service never accepts a browser ledger ID, owner ID, projection,
award or balance. It supports ordinary non-terminal choices only; lifecycle,
terminal and achievement transitions remain fail-closed.
"""
from __future__ import annotations

from typing import Any, Mapping

from .attributed_mongo_reservations import AttributedMongoReservationStore
from .attribution import AttributionUnproven, require_event_attribution
from .canonical_event import canonical_event_sha256
from .choice_checkpoint_guard import CheckpointConflict
from .mongo_reservations import (
    ProgressionConflict, ReservationBusy, ReservationInvariantError,
)
from .strict_event_input import StrictChoiceEvent
from .trusted_choice_reservation import plan_account_choice_reservation
from .trusted_content import InvalidChoice, UnknownContentVersion
from .trusted_owner import ProgressionAccessDenied, require_account_ledger_owner


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


async def process_account_choice(
    ledgers: Any, events: Any, registry: Mapping[str, Any], *,
    authenticated_user_id: str, event: StrictChoiceEvent,
) -> dict:
    """Validate, reserve, commit and reconcile one account-owned choice."""
    if not isinstance(event, StrictChoiceEvent):
        raise TrustedChoiceValidationError("ordinary choice event required")
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
            return {"status": "duplicate", "eventId": event.eventId,
                    "ledger": public_account_ledger(ledger)}
        if existing.get("status") == "committing":
            try:
                await store.recover(existing)
            except ReservationBusy as exc:
                raise TrustedChoiceIndeterminate("event is still being reconciled") from exc
            except (AttributionUnproven, ProgressionConflict,
                    ReservationInvariantError) as exc:
                raise TrustedChoiceIndeterminate("event reconciliation failed closed") from exc
            confirmed = await _owned_ledger(ledgers, authenticated_user_id)
            return {"status": "duplicate", "eventId": event.eventId,
                    "ledger": public_account_ledger(confirmed)}

    try:
        plan = plan_account_choice_reservation(
            registry, ledger, event,
            authenticated_user_id=authenticated_user_id,
        )
        reserved = await store.reserve(**plan)
        if reserved.get("status") == "applied":
            require_event_attribution(ledger, reserved)
            return {"status": "duplicate", "eventId": event.eventId,
                    "ledger": public_account_ledger(ledger)}
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
    return {"status": "confirmed", "eventId": event.eventId,
            "ledger": public_account_ledger(confirmed)}
