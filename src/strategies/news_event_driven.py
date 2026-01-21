from __future__ import annotations
import time
from typing import Dict, List

from alpaca.trading.enums import OrderSide, TimeInForce

from .base import Strategy
from ..data_stream import MarketDataStream
from ..execution import OrderIntent
from ..risk import PositionState


class NewsEventDriven(Strategy):
    name = "news"

    def __init__(self, symbols: List[str], keywords: List[str] | None = None, notional: float = 500.0, max_hold_sec: int = 300):
        super().__init__(symbols)
        self.keywords = keywords or ["earnings", "guidance", "beats", "misses", "acquisition", "merger", "sec", "investigation"]
        self.notional = notional
        self.max_hold_sec = max_hold_sec
        self.events: List[dict] = []
        self.active: Dict[str, dict] = {}

    def on_news(self, symbol: str, headline: str) -> None:
        text = headline.lower()
        if any(k in text for k in self.keywords):
            self.events.append({"symbol": symbol, "headline": headline, "ts": time.time()})

    def on_tick(self, data: MarketDataStream, positions: Dict[str, PositionState]) -> List[OrderIntent]:
        intents: List[OrderIntent] = []
        now = time.time()
        for sym, info in list(self.active.items()):
            if now - info["ts"] > self.max_hold_sec:
                st = data.states.get(sym)
                if not st or st.mid <= 0:
                    continue
                pos = positions.get(sym)
                if pos and pos.qty != 0:
                    side = OrderSide.SELL if pos.qty > 0 else OrderSide.BUY
                    intents.append(self._mk_intent(sym, side, abs(pos.qty), st.mid, TimeInForce.DAY, f"{sym}-news-flat", order_type="market"))
                self.active.pop(sym, None)
        while self.events:
            ev = self.events.pop(0)
            sym = ev["symbol"]
            st = data.states.get(sym)
            if not st or st.mid <= 0:
                continue
            qty = max(1, int(self.notional / st.mid))
            intents.append(self._mk_intent(sym, OrderSide.BUY, qty, st.mid * 1.002, TimeInForce.DAY, f"{sym}-news-long"))
            self.active[sym] = {"ts": now}
        return intents
