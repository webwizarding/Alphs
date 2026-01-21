from __future__ import annotations
import time
from typing import Dict, List

from alpaca.trading.enums import OrderSide, TimeInForce

from .base import Strategy
from ..data_stream import MarketDataStream
from ..execution import OrderIntent
from ..risk import PositionState


class LeadLagArb(Strategy):
    name = "leadlag"

    def __init__(self, leader: str, laggers: List[str], threshold: float = 0.0015, max_hold_sec: int = 120, notional: float = 1000.0):
        symbols = [leader] + laggers
        super().__init__(symbols)
        self.leader = leader
        self.laggers = laggers
        self.threshold = threshold
        self.max_hold_sec = max_hold_sec
        self.notional = notional
        self.active: Dict[str, dict] = {}

    def on_tick(self, data: MarketDataStream, positions: Dict[str, PositionState]) -> List[OrderIntent]:
        intents: List[OrderIntent] = []
        leader_state = data.states.get(self.leader)
        if not leader_state or len(leader_state.mid_window) < 5:
            return []
        leader_ret = self._recent_return(leader_state)
        now = time.time()
        for sym in self.laggers:
            st = data.states.get(sym)
            if not st or len(st.mid_window) < 5:
                continue
            lag_ret = self._recent_return(st)
            residual = leader_ret - lag_ret
            active = self.active.get(sym)
            if active:
                if abs(residual) < self.threshold / 2 or now - active["ts"] > self.max_hold_sec:
                    pos = positions.get(sym)
                    if pos and pos.qty != 0:
                        side = OrderSide.SELL if pos.qty > 0 else OrderSide.BUY
                        intents.append(self._mk_intent(sym, side, abs(pos.qty), st.mid, TimeInForce.DAY, f"{sym}-flat", order_type="market"))
                    self.active.pop(sym, None)
                continue
            if abs(leader_ret) < self.threshold:
                continue
            if residual > self.threshold:
                qty = max(1, int(self.notional / st.mid))
                intents.append(self._mk_intent(sym, OrderSide.BUY, qty, st.mid * 1.001, TimeInForce.DAY, f"{sym}-ll-long"))
                self.active[sym] = {"ts": now, "dir": "long"}
            elif residual < -self.threshold:
                qty = max(1, int(self.notional / st.mid))
                intents.append(self._mk_intent(sym, OrderSide.SELL, qty, st.mid * 0.999, TimeInForce.DAY, f"{sym}-ll-short"))
                self.active[sym] = {"ts": now, "dir": "short"}
        return intents

    def _recent_return(self, st) -> float:
        vals = st.mid_window.values()
        if len(vals) < 5:
            return 0.0
        return (vals[-1] - vals[-5]) / vals[-5]
