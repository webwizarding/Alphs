from __future__ import annotations
import time
from typing import Dict, List, Tuple

from alpaca.trading.enums import OrderSide, TimeInForce

from .base import Strategy
from ..data_stream import MarketDataStream
from ..execution import OrderIntent
from ..risk import PositionState
from ..utils.rolling import RollingWindow
from ..utils.math import zscore


class ETFBasketArb(Strategy):
    name = "etf"

    def __init__(self, etf_pairs: List[str], baskets: Dict[str, str], window: int = 300, entry_z: float = 2.0, exit_z: float = 0.5, max_hold_sec: int = 300, notional: float = 1000.0):
        symbols = list({s for p in etf_pairs for s in p.split("/")})
        for etf, basket in baskets.items():
            symbols.append(etf)
            for item in basket.split(","):
                sym = item.split(":")[0].strip().upper()
                if sym:
                    symbols.append(sym)
        super().__init__(list(dict.fromkeys(symbols)))
        self.etf_pairs = [tuple(p.split("/")) for p in etf_pairs]
        self.baskets = self._parse_baskets(baskets)
        self.window = window
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.max_hold_sec = max_hold_sec
        self.notional = notional
        self.spreads: Dict[Tuple[str, str], RollingWindow] = {p: RollingWindow(window) for p in self.etf_pairs}
        self.active_pairs: Dict[Tuple[str, str], dict] = {}
        self.active_baskets: Dict[str, dict] = {}

    def on_tick(self, data: MarketDataStream, positions: Dict[str, PositionState]) -> List[OrderIntent]:
        intents: List[OrderIntent] = []
        now = time.time()
        for p in self.etf_pairs:
            e1, e2 = p
            st1 = data.states.get(e1)
            st2 = data.states.get(e2)
            if not st1 or not st2 or st1.mid <= 0 or st2.mid <= 0:
                continue
            spread = st1.mid - st2.mid
            w = self.spreads[p]
            w.add(spread)
            if len(w) < 30:
                continue
            z = zscore(spread, w.mean(), w.std())
            active = self.active_pairs.get(p)
            if active:
                if abs(z) < self.exit_z or now - active["ts"] > self.max_hold_sec:
                    intents.extend(self._flatten_pair(p, positions, st1.mid, st2.mid))
                    self.active_pairs.pop(p, None)
                continue
            if z > self.entry_z:
                intents.extend(self._enter_pair(p, "short", st1.mid, st2.mid))
                self.active_pairs[p] = {"ts": now}
            elif z < -self.entry_z:
                intents.extend(self._enter_pair(p, "long", st1.mid, st2.mid))
                self.active_pairs[p] = {"ts": now}
        for etf, basket in self.baskets.items():
            st_etf = data.states.get(etf)
            if not st_etf or st_etf.mid <= 0:
                continue
            basket_value = 0.0
            for sym, w in basket:
                st = data.states.get(sym)
                if not st or st.mid <= 0:
                    basket_value = 0.0
                    break
                basket_value += st.mid * w
            if basket_value <= 0:
                continue
            diff = st_etf.mid - basket_value
            active = self.active_baskets.get(etf)
            if active:
                if abs(diff) < st_etf.mid * 0.001 or now - active["ts"] > self.max_hold_sec:
                    intents.extend(self._flatten_symbol(etf, positions, st_etf.mid))
                    self.active_baskets.pop(etf, None)
                continue
            if diff > st_etf.mid * 0.003:
                intents.extend(self._enter_symbol(etf, "short", st_etf.mid))
                self.active_baskets[etf] = {"ts": now}
            elif diff < -st_etf.mid * 0.003:
                intents.extend(self._enter_symbol(etf, "long", st_etf.mid))
                self.active_baskets[etf] = {"ts": now}
        return intents

    def _parse_baskets(self, raw: Dict[str, str]) -> Dict[str, List[tuple]]:
        out: Dict[str, List[tuple]] = {}
        for etf, val in raw.items():
            items = []
            for item in val.split(","):
                if not item.strip():
                    continue
                sym, w = item.split(":")
                items.append((sym.strip().upper(), float(w)))
            out[etf] = items
        return out

    def _enter_pair(self, pair: Tuple[str, str], direction: str, p1: float, p2: float) -> List[OrderIntent]:
        e1, e2 = pair
        qty1 = max(1, int(self.notional / p1))
        qty2 = max(1, int(self.notional / p2))
        if direction == "long":
            i1 = self._mk_intent(e1, OrderSide.BUY, qty1, p1 * 1.001, TimeInForce.DAY, f"{e1}-{e2}-long")
            i2 = self._mk_intent(e2, OrderSide.SELL, qty2, p2 * 0.999, TimeInForce.DAY, f"{e1}-{e2}-long2")
        else:
            i1 = self._mk_intent(e1, OrderSide.SELL, qty1, p1 * 0.999, TimeInForce.DAY, f"{e1}-{e2}-short")
            i2 = self._mk_intent(e2, OrderSide.BUY, qty2, p2 * 1.001, TimeInForce.DAY, f"{e1}-{e2}-short2")
        return [i1, i2]

    def _flatten_pair(self, pair: Tuple[str, str], positions: Dict[str, PositionState], p1: float, p2: float) -> List[OrderIntent]:
        e1, e2 = pair
        intents: List[OrderIntent] = []
        intents.extend(self._flatten_symbol(e1, positions, p1))
        intents.extend(self._flatten_symbol(e2, positions, p2))
        return intents

    def _enter_symbol(self, symbol: str, direction: str, price: float) -> List[OrderIntent]:
        qty = max(1, int(self.notional / price))
        if direction == "long":
            return [self._mk_intent(symbol, OrderSide.BUY, qty, price * 1.001, TimeInForce.DAY, f"{symbol}-etf-long")]
        return [self._mk_intent(symbol, OrderSide.SELL, qty, price * 0.999, TimeInForce.DAY, f"{symbol}-etf-short")]

    def _flatten_symbol(self, symbol: str, positions: Dict[str, PositionState], price: float) -> List[OrderIntent]:
        pos = positions.get(symbol)
        if not pos or pos.qty == 0:
            return []
        side = OrderSide.SELL if pos.qty > 0 else OrderSide.BUY
        return [self._mk_intent(symbol, side, abs(pos.qty), price, TimeInForce.DAY, f"{symbol}-flat", order_type="market")]
