"""Inert, versioned canonical event fingerprint; no route, lookup or persistence.

This is a v1 *choice/lifecycle event* format, not generic JSON canonicalization.
Cross-language implementations must match the UTF-8 fixture bytes exactly.
"""
import hashlib
import json
import re
from typing import Any

from pydantic import TypeAdapter

from .strict_event_input import StrictProgressionEvent

_EVENT = TypeAdapter(StrictProgressionEvent)
_UUID4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def canonical_event_bytes(payload: Any) -> bytes:
    """Validate known fields and UUID v4, then encode deterministic v1 JSON.

    No whitespace; lexicographically sorted ASCII field names; UTF-8 text
    (non-ASCII unescaped); JSON integer numbers; no optional/default fields.
    Reject unknown fields and coercion before encoding. UUID is lowercase,
    hyphenated, version 4 and RFC 4122 variant. The event ID participates
    in the hash; caller supplies ledger scope separately for deduplication.
    """
    event = _EVENT.validate_python(payload, strict=True)
    if not _UUID4.fullmatch(event.eventId):
        raise ValueError("eventId must be a lowercase RFC 4122 UUID v4")
    data = event.model_dump(mode="json", exclude_unset=True)
    return json.dumps(data, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def canonical_event_sha256(payload: Any) -> str:
    """Lowercase hex SHA-256 of canonical_event_bytes(payload)."""
    return hashlib.sha256(canonical_event_bytes(payload)).hexdigest()
