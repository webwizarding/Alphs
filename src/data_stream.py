from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from alpaca.data.live import StockDataStream
from alpaca.data.enums import DataFeed

from .utils.rolling import RollingWindow


@dataclass
class SymbolState:
    symbol: str
    bid: float = 0.0
    ask: float = 0.0
    bid_size: float = 0.0
    ask_size: float = 0.0
    last_trade: float = 0.0
    last_trade_size: float = 0.0
    last_update_ts: float = 0.0
    last_trade_ts: float = 0.0
    last_bar_close: float = 0.0
    mid: float = 0.0
    mid_window: RollingWindow = field(default_factory=lambda: RollingWindow(600))
    ret_window: RollingWindow = field(default_factory=lambda: RollingWindow(600))
    spread_window: RollingWindow = field(default_factory=lambda: RollingWindow(600))

    def update_quote(self, bid: float, ask: float, bid_size: float, ask_size: float, ts: float) -> None:
        self.bid = bid
        self.ask = ask
        self.bid_size = bid_size
        self.ask_size = ask_size
        self.last_update_ts = ts
        if bid > 0 and ask > 0:
            mid = (bid + ask) / 2.0
            if self.mid > 0:
                ret = (mid - self.mid) / self.mid
                self.ret_window.add(ret)
            self.mid = mid
            self.mid_window.add(mid)
            self.spread_window.add(ask - bid)

    def update_trade(self, price: float, size: float, ts: float) -> None:
        self.last_trade = price
        self.last_trade_size = size
        self.last_trade_ts = ts

    def update_bar(self, close: float, ts: float) -> None:
        self.last_bar_close = close
        self.last_update_ts = ts

    def quote_stale(self, max_age_sec: float) -> bool:
        return time.time() - self.last_update_ts > max_age_sec

    def mid_returns_std(self) -> float:
        return self.ret_window.std()


class MarketDataStream:
    def __init__(self, api_key: str, api_secret: str, symbols: List[str], feed: str = "iex"):
        self.api_key = api_key
        self.api_secret = api_secret
        self.symbols = symbols
        self.feed = feed
        self.states: Dict[str, SymbolState] = {s: SymbolState(symbol=s) for s in symbols}
        self._stream = StockDataStream(api_key, api_secret, feed=DataFeed(feed))
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._stream.subscribe_quotes(self._on_quote, *self.symbols)
        self._stream.subscribe_trades(self._on_trade, *self.symbols)
        self._stream.subscribe_bars(self._on_bar, *self.symbols)
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

    async def _on_quote(self, q) -> None:
        state = self.states.get(q.symbol)
        if not state:
            return
        ts = q.timestamp.timestamp() if q.timestamp else time.time()
        state.update_quote(float(q.bid_price), float(q.ask_price), float(q.bid_size), float(q.ask_size), ts)

    async def _on_trade(self, t) -> None:
        state = self.states.get(t.symbol)
        if not state:
            return
        ts = t.timestamp.timestamp() if t.timestamp else time.time()
        state.update_trade(float(t.price), float(t.size), ts)

    async def _on_bar(self, b) -> None:
        state = self.states.get(b.symbol)
        if not state:
            return
        ts = b.timestamp.timestamp() if b.timestamp else time.time()
        state.update_bar(float(b.close), ts)
