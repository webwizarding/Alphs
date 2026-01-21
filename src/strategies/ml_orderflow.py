from __future__ import annotations
import time
from typing import Dict, List, Tuple
import numpy as np
from sklearn.linear_model import SGDClassifier

from alpaca.trading.enums import OrderSide, TimeInForce

from .base import Strategy
from ..data_stream import MarketDataStream
from ..execution import OrderIntent
from ..risk import PositionState


class MLOrderflow(Strategy):
    name = "ml"

    def __init__(self, symbols: List[str], horizon_sec: int = 5, prob_threshold: float = 0.6, notional: float = 500.0, max_hold_sec: int = 60, min_trade_interval_sec: int = 5):
        super().__init__(symbols)
        self.horizon_sec = horizon_sec
        self.prob_threshold = prob_threshold
        self.notional = notional
        self.max_hold_sec = max_hold_sec
        self.min_trade_interval_sec = min_trade_interval_sec
        self.models: Dict[str, SGDClassifier] = {s: SGDClassifier(loss="log_loss", max_iter=1, learning_rate="optimal") for s in symbols}
        self.buffers: Dict[str, List[Tuple[float, np.ndarray, float]]] = {s: [] for s in symbols}
        self.active: Dict[str, dict] = {}
        self.trained: Dict[str, bool] = {s: False for s in symbols}
        self.last_trade_ts: Dict[str, float] = {s: 0.0 for s in symbols}
        self.last_reset_ts: Dict[str, float] = {s: time.time() for s in symbols}

    def on_tick(self, data: MarketDataStream, positions: Dict[str, PositionState]) -> List[OrderIntent]:
        intents: List[OrderIntent] = []
        now = time.time()
        for sym in self.symbols:
            st = data.states.get(sym)
            if not st or st.mid <= 0 or st.bid <= 0 or st.ask <= 0:
                continue
            if now - self.last_reset_ts[sym] > 3600:
                self.models[sym] = SGDClassifier(loss="log_loss", max_iter=1, learning_rate="optimal")
                self.trained[sym] = False
                self.buffers[sym].clear()
                self.last_reset_ts[sym] = now
            features = self._features(st)
            self.buffers[sym].append((now, features, st.mid))
            self._train(sym, now, st.mid)

            active = self.active.get(sym)
            if active and now - active["ts"] > self.max_hold_sec:
                pos = positions.get(sym)
                if pos and pos.qty != 0:
                    side = OrderSide.SELL if pos.qty > 0 else OrderSide.BUY
                    intents.append(self._mk_intent(sym, side, abs(pos.qty), st.mid, TimeInForce.DAY, f"{sym}-ml-flat", order_type="market"))
                self.active.pop(sym, None)

            if not self.trained[sym]:
                continue
            model = self.models[sym]
            prob = model.predict_proba([features])[0]
            up_prob = prob[1]
            down_prob = prob[0]
            if up_prob > self.prob_threshold and now - self.last_trade_ts[sym] > self.min_trade_interval_sec:
                qty = max(1, int(self.notional / st.mid))
                intents.append(self._mk_intent(sym, OrderSide.BUY, qty, st.mid * 1.001, TimeInForce.DAY, f"{sym}-ml-long"))
                self.active[sym] = {"ts": now}
                self.last_trade_ts[sym] = now
            elif down_prob > self.prob_threshold and now - self.last_trade_ts[sym] > self.min_trade_interval_sec:
                qty = max(1, int(self.notional / st.mid))
                intents.append(self._mk_intent(sym, OrderSide.SELL, qty, st.mid * 0.999, TimeInForce.DAY, f"{sym}-ml-short"))
                self.active[sym] = {"ts": now}
                self.last_trade_ts[sym] = now
        return intents

    def _features(self, st) -> np.ndarray:
        spread = st.ask - st.bid
        imbalance = 0.0
        if st.bid_size + st.ask_size > 0:
            imbalance = (st.bid_size - st.ask_size) / (st.bid_size + st.ask_size)
        ret = st.ret_window.last() if len(st.ret_window) > 0 else 0.0
        vol = st.ret_window.std()
        trade_imb = 0.0
        if st.last_trade > 0 and st.mid > 0:
            trade_imb = 1.0 if st.last_trade > st.mid else -1.0
        return np.array([spread, imbalance, ret, trade_imb, vol], dtype=float)

    def _train(self, sym: str, now: float, mid_now: float) -> None:
        buf = self.buffers[sym]
        model = self.models[sym]
        while buf and now - buf[0][0] >= self.horizon_sec:
            ts, feat, mid_then = buf.pop(0)
            label = 1 if mid_now > mid_then else 0
            if not self.trained[sym]:
                model.partial_fit([feat], [label], classes=[0, 1])
                self.trained[sym] = True
            else:
                model.partial_fit([feat], [label])
