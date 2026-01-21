from __future__ import annotations
import asyncio
from typing import Awaitable, Callable, List, Optional

from alpaca.trading.stream import TradingStream


class TradeStream:
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self._stream = TradingStream(api_key, api_secret, paper=True)
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._handlers: List[Callable[[dict], Awaitable[None]]] = []

    def add_handler(self, handler: Callable[[dict], Awaitable[None]]) -> None:
        self._handlers.append(handler)

    async def start(self) -> None:
        self._running = True
        self._stream.subscribe_trade_updates(self._on_update)
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._running = False
        if self._stream:
            await self._stream.stop_ws()
        if self._task:
            await self._task

    async def _run_loop(self) -> None:
        backoff = 1.0
        while self._running:
            try:
                await asyncio.to_thread(self._stream.run)
                backoff = 1.0
            except Exception:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)

    async def _on_update(self, data) -> None:
        payload = data.dict() if hasattr(data, "dict") else data
        for handler in self._handlers:
            await handler(payload)
