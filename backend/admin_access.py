"""Small, fail-closed admin allow-list helpers for Phase 7."""
from typing import Iterable


def configured_admin_emails(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {
        email.strip().lower()
        for email in raw.split(",")
        if email.strip() and "@" in email.strip()
    }


def is_admin_email(email: object, configured: Iterable[str]) -> bool:
    return isinstance(email, str) and email.strip().lower() in set(configured)
