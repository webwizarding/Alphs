from __future__ import annotations
import asyncio
import time
from typing import Awaitable, Callable


class AsyncScheduler:
    def __init__(self, interval_sec: float):
        self.interval_sec = interval_sec
        self._running = False

    async def start(self, tick: Callable[[], Awaitable[None]]) -> None:
        self._running = True
        next_ts = time.monotonic()
        while self._running:
            now = time.monotonic()
            if now >= next_ts:
                await tick()
                next_ts = now + self.interval_sec
            await asyncio.sleep(0.01)

    def stop(self) -> None:
        self._running = False
