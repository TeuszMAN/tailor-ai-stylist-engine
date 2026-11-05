"""In-memory sliding-window rate limiter (no I/O, no framework dependency).

Used by the HTTP layer (per-client limits) and by the agent (global LLM budget).
It is per process: with several replicas, enforce global limits at the gateway (or Redis).
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    limit: int
    window_seconds: float = 60.0


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int


class SlidingWindowRateLimiter:
    """Keeps the timestamps of the last `limit` hits per key and rejects the next one inside the window."""

    def __init__(self, clock: Callable[[], float] = time.monotonic, max_keys: int = 10_000) -> None:
        self._clock = clock
        self._max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, rule: RateLimitRule) -> RateLimitDecision:
        if rule.limit <= 0:  # a zero budget means "never allowed"
            return RateLimitDecision(
                allowed=False, limit=0, remaining=0, retry_after_seconds=max(1, math.ceil(rule.window_seconds))
            )
        now = self._clock()
        cutoff = now - rule.window_seconds
        with self._lock:
            window = self._hits.setdefault(key, deque())
            while window and window[0] <= cutoff:
                window.popleft()
            if len(window) >= rule.limit:
                retry_after = max(1, math.ceil(window[0] + rule.window_seconds - now))
                return RateLimitDecision(allowed=False, limit=rule.limit, remaining=0, retry_after_seconds=retry_after)
            window.append(now)
            if len(self._hits) > self._max_keys:
                self._evict(cutoff)
            return RateLimitDecision(
                allowed=True, limit=rule.limit, remaining=rule.limit - len(window), retry_after_seconds=0
            )

    def _evict(self, cutoff: float) -> None:
        """Drop keys without hits inside the current window (bounded memory under many clients)."""
        stale = [key for key, window in self._hits.items() if not window or window[-1] <= cutoff]
        for key in stale:
            del self._hits[key]

    @property
    def tracked_keys(self) -> int:
        return len(self._hits)
