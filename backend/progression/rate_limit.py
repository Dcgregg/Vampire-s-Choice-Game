"""Bounded defense-in-depth rate limiter for opt-in progression routes."""
from collections import OrderedDict, deque
import logging
from time import monotonic
from typing import Callable

from fastapi import HTTPException

logger = logging.getLogger("trusted_progression")


class AccountRateLimiter:
    def __init__(
        self, *, limit: int = 60, window_seconds: int = 60,
        max_accounts: int = 10_000, clock: Callable[[], float] = monotonic,
    ):
        if limit <= 0 or window_seconds <= 0 or max_accounts <= 0:
            raise ValueError("positive rate limit settings required")
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_accounts = max_accounts
        self.clock = clock
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()

    def require(self, owner_id: str) -> None:
        """Allow one request or raise a stable 429 without exposing identity."""
        if not isinstance(owner_id, str) or not owner_id:
            raise HTTPException(status_code=401, detail={"error": "not_authenticated"})
        now = self.clock()
        hits = self._hits.pop(owner_id, deque())
        cutoff = now - self.window_seconds
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= self.limit:
            logger.warning(
                "trusted_progression_outcome",
                extra={"progression_kind": "request",
                       "progression_status": "rate_limited"},
            )
            self._hits[owner_id] = hits
            retry_after = max(1, int(hits[0] + self.window_seconds - now) + 1)
            raise HTTPException(
                status_code=429,
                detail={"error": "progression_rate_limited", "retryable": True},
                headers={"Retry-After": str(retry_after),
                         "Cache-Control": "no-store", "Pragma": "no-cache"},
            )
        hits.append(now)
        self._hits[owner_id] = hits
        while len(self._hits) > self.max_accounts:
            self._hits.popitem(last=False)
