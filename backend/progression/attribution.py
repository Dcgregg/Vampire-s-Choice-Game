"""Pure, fail-closed event attribution predicate; not wired into persistence.

A future transactional writer must atomically retain immutable attribution for
*every* committed revision. This predicate cannot establish that such writes
are exclusive or that the history was not tampered with; those are separate
persistence and authorization requirements.
"""
from __future__ import annotations

from typing import Any, Mapping


class AttributionUnproven(Exception):
    """Do not finalise or report an event applied without durable proof."""


def require_event_attribution(ledger: Mapping[str, Any], event: Mapping[str, Any]) -> None:
    """Require an exact retained revision-to-event binding, even after later writes.

    The proposed ``appliedEventIds`` mapping uses string revision keys because
    MongoDB document field names are strings. This is a *candidate contract*,
    not a migration or an assertion that existing ledgers contain this field.
    """
    base, target = event.get("baseRevision"), event.get("targetRevision")
    if type(base) is not int or base < 0 or type(target) is not int or target != base + 1:
        raise AttributionUnproven("invalid event revision")
    ledger_revision = ledger.get("progressionRevision")
    if type(ledger_revision) is not int or ledger_revision < target:
        raise AttributionUnproven("target revision not committed")
    ledger_id, event_id = event.get("ledgerId"), event.get("eventId")
    if ledger_id is None or not isinstance(event_id, str) or not event_id:
        raise AttributionUnproven("missing event identity")
    if ledger.get("_id") != ledger_id:
        raise AttributionUnproven("event belongs to another ledger")
    history = ledger.get("appliedEventIds")
    if not isinstance(history, Mapping) or history.get(str(target)) != event_id:
        raise AttributionUnproven("no matching durable event attribution")
