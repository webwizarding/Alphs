from __future__ import annotations
import time
import asyncio


class TokenBucket:
    def __init__(self, rate_per_sec: float, capacity: int):
        self.rate_per_sec = rate_per_sec
        self.capacity = capacity
        self.tokens = capacity
        self.updated = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        delta = now - self.updated
        if delta <= 0:
            return
        self.tokens = min(self.capacity, self.tokens + delta * self.rate_per_sec)
        self.updated = now

    async def acquire(self, tokens: int = 1) -> None:
        while True:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return
            await asyncio.sleep(0.05)
