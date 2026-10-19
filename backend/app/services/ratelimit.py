"""A small in-memory sliding-window limiter.

Per process: with several API instances each keeps its own counts, so the real limit is
looser. It is a brake on guessing passwords and mass sign-ups, not a replacement for a
WAF or a shared limiter (see docs/deployment-aws.md).
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable


class RateLimiter:
    def __init__(
        self, max_events: int, window_seconds: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.max_events = max_events
        self.window = window_seconds
        self._clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str) -> deque[float]:
        events = self._events[key]
        cutoff = self._clock() - self.window
        while events and events[0] <= cutoff:
            events.popleft()
        if not events:
            self._events.pop(key, None)
            return self._events[key]
        return events

    def hit(self, key: str) -> None:
        self._prune(key).append(self._clock())

    def blocked(self, key: str) -> bool:
        return len(self._prune(key)) >= self.max_events

    def retry_after(self, key: str) -> int:
        events = self._prune(key)
        if len(events) < self.max_events:
            return 0
        return max(1, int(events[0] + self.window - self._clock()) + 1)

    def reset(self, key: str) -> None:
        self._events.pop(key, None)

    def clear(self) -> None:
        self._events.clear()


class Limiters:
    """The limiters the auth routes use. Tests replace or clear them."""

    def __init__(self) -> None:
        self.login_by_email = RateLimiter(max_events=5, window_seconds=15 * 60)
        self.login_by_ip = RateLimiter(max_events=25, window_seconds=15 * 60)
        self.register_by_ip = RateLimiter(max_events=10, window_seconds=60 * 60)

    def clear(self) -> None:
        for limiter in (self.login_by_email, self.login_by_ip, self.register_by_ip):
            limiter.clear()


limiters = Limiters()
