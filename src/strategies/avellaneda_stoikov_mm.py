from __future__ import annotations
import time
from typing import Dict, List
import math

from alpaca.trading.enums import OrderSide, TimeInForce

from .base import Strategy
from ..data_stream import MarketDataStream
from ..execution import OrderIntent
from ..risk import PositionState


class AvellanedaStoikovMM(Strategy):
    name = "mm"

    def __init__(self, symbols: List[str], gamma: float = 0.1, k: float = 1.5, size: int = 5, refresh_ms: int = 1000, max_inventory: int = 50):
        super().__init__(symbols)
        self.gamma = gamma
        self.k = k
        self.size = size
        self.refresh_ms = refresh_ms
        self.max_inventory = max_inventory
        self.last_refresh = 0.0

    def on_tick(self, data: MarketDataStream, positions: Dict[str, PositionState]) -> List[OrderIntent]:
        now = time.time()
        if (now - self.last_refresh) * 1000 < self.refresh_ms:
            return []
        self.last_refresh = now
        intents: List[OrderIntent] = []
        for sym in self.symbols:
            st = data.states.get(sym)
            if not st or st.mid <= 0 or st.bid <= 0 or st.ask <= 0:
                continue
            spread = st.ask - st.bid
            if spread <= 0 or st.quote_stale(5.0):
                continue
            sigma = st.mid_returns_std()
            pos = positions.get(sym)
            q = pos.qty if pos else 0.0
            if abs(q) > self.max_inventory:
                side = OrderSide.SELL if q > 0 else OrderSide.BUY
                intents.append(self._mk_intent(sym, side, abs(q), st.mid, TimeInForce.DAY, f"{sym}-panic", order_type="market"))
                continue
            t_horizon = 30.0
            reservation = st.mid - q * self.gamma * (sigma ** 2) * t_horizon
            delta = max(spread / 2, (self.gamma * (sigma ** 2) * t_horizon) + (1.0 / self.gamma) * math.log(1 + self.gamma / self.k))
            bid = reservation - delta
            ask = reservation + delta
            if bid <= 0 or ask <= 0:
                continue
            if q > 0:
                bid *= 0.999
                ask *= 0.998
            elif q < 0:
                bid *= 1.002
                ask *= 1.001
            intents.append(self._mk_intent(sym, OrderSide.BUY, self.size, bid, TimeInForce.DAY, f"{sym}-bid"))
            intents.append(self._mk_intent(sym, OrderSide.SELL, self.size, ask, TimeInForce.DAY, f"{sym}-ask"))
        return intents
