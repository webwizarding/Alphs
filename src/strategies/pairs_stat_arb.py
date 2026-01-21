from __future__ import annotations
import time
from typing import Dict, List, Tuple
import numpy as np

from alpaca.trading.enums import OrderSide, TimeInForce

from .base import Strategy
from ..data_stream import MarketDataStream
from ..execution import OrderIntent
from ..risk import PositionState
from ..utils.rolling import RollingWindow
from ..utils.math import zscore, ols_beta


class PairsStatArb(Strategy):
    name = "pairs"

    def __init__(self, pairs: List[str], window: int = 600, entry_z: float = 2.0, exit_z: float = 0.5, max_hold_sec: int = 300, notional: float = 1000.0):
        symbols = list({s for p in pairs for s in p.split("/")})
        super().__init__(symbols)
        self.pairs = [tuple(p.split("/")) for p in pairs]
        self.window = window
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.max_hold_sec = max_hold_sec
        self.notional = notional
        self.spreads: Dict[Tuple[str, str], RollingWindow] = {p: RollingWindow(window) for p in self.pairs}
        self.beta: Dict[Tuple[str, str], float] = {p: 1.0 for p in self.pairs}
        self.last_beta_ts = 0.0
        self.active: Dict[Tuple[str, str], dict] = {}

    def on_tick(self, data: MarketDataStream, positions: Dict[str, PositionState]) -> List[OrderIntent]:
        intents: List[OrderIntent] = []
        now = time.time()
        for p in self.pairs:
            s1, s2 = p
            st1 = data.states.get(s1)
            st2 = data.states.get(s2)
            if not st1 or not st2 or st1.mid <= 0 or st2.mid <= 0:
                continue
            if now - self.last_beta_ts > 60:
                x = st2.mid_window.values()
                y = st1.mid_window.values()
                if len(x) >= 50 and len(y) >= 50:
                    self.beta[p] = ols_beta(x, y)
                self.last_beta_ts = now
            spread = st1.mid - self.beta[p] * st2.mid
            w = self.spreads[p]
            w.add(spread)
            if len(w) < 30:
                continue
            z = zscore(spread, w.mean(), w.std())
            active = self.active.get(p)
            if active:
                if abs(z) < self.exit_z or now - active["ts"] > self.max_hold_sec:
                    intents.extend(self._flatten_pair(p, positions, st1.mid, st2.mid))
                    self.active.pop(p, None)
                continue
            if z > self.entry_z:
                intents.extend(self._enter_pair(p, "short", positions, st1.mid, st2.mid))
                self.active[p] = {"ts": now, "dir": "short"}
            elif z < -self.entry_z:
                intents.extend(self._enter_pair(p, "long", positions, st1.mid, st2.mid))
                self.active[p] = {"ts": now, "dir": "long"}
        return intents

    def _enter_pair(self, pair: Tuple[str, str], direction: str, positions: Dict[str, PositionState], p1: float, p2: float) -> List[OrderIntent]:
        s1, s2 = pair
        beta = self.beta[pair]
        qty1 = max(1, int(self.notional / p1))
        qty2 = max(1, int((self.notional * abs(beta)) / p2))
        if direction == "long":
            i1 = self._mk_intent(s1, OrderSide.BUY, qty1, p1 * 1.001, TimeInForce.DAY, f"{s1}-{s2}-long")
            i2 = self._mk_intent(s2, OrderSide.SELL, qty2, p2 * 0.999, TimeInForce.DAY, f"{s1}-{s2}-long2")
        else:
            i1 = self._mk_intent(s1, OrderSide.SELL, qty1, p1 * 0.999, TimeInForce.DAY, f"{s1}-{s2}-short")
            i2 = self._mk_intent(s2, OrderSide.BUY, qty2, p2 * 1.001, TimeInForce.DAY, f"{s1}-{s2}-short2")
        return [i1, i2]

    def _flatten_pair(self, pair: Tuple[str, str], positions: Dict[str, PositionState], p1: float, p2: float) -> List[OrderIntent]:
        s1, s2 = pair
        intents: List[OrderIntent] = []
        pos1 = positions.get(s1)
        pos2 = positions.get(s2)
        if pos1 and pos1.qty != 0:
            side = OrderSide.SELL if pos1.qty > 0 else OrderSide.BUY
            intents.append(self._mk_intent(s1, side, abs(pos1.qty), p1, TimeInForce.DAY, f"{s1}-{s2}-flat1", order_type="market"))
        if pos2 and pos2.qty != 0:
            side = OrderSide.SELL if pos2.qty > 0 else OrderSide.BUY
            intents.append(self._mk_intent(s2, side, abs(pos2.qty), p2, TimeInForce.DAY, f"{s1}-{s2}-flat2", order_type="market"))
        return intents
