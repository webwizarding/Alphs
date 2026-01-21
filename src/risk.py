from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List
import time

from alpaca.trading.enums import OrderSide

from .execution import OrderIntent
from .data_stream import MarketDataStream


@dataclass
class PositionState:
    symbol: str
    qty: float
    avg_price: float


class RiskManager:
    def __init__(self, max_gross: float, max_net: float, max_order_notional: float, max_pos_notional: float, daily_loss_limit: float):
        self.max_gross = max_gross
        self.max_net = max_net
        self.max_order_notional = max_order_notional
        self.max_pos_notional = max_pos_notional
        self.daily_loss_limit = daily_loss_limit
        self.start_equity: float | None = None
        self.kill_switch = False
        self.last_account_check = 0.0

    def update_account(self, equity: float) -> None:
        if self.start_equity is None:
            self.start_equity = equity
        if self.start_equity - equity >= self.daily_loss_limit:
            self.kill_switch = True

    def check(self, intents: List[OrderIntent], positions: Dict[str, PositionState], data: MarketDataStream) -> List[OrderIntent]:
        if self.kill_switch:
            return []
        gross = 0.0
        net = 0.0
        for sym, pos in positions.items():
            price = data.states.get(sym).mid if sym in data.states else pos.avg_price
            notional = pos.qty * price
            gross += abs(notional)
            net += notional
        if gross > self.max_gross or abs(net) > self.max_net:
            return []
        filtered: List[OrderIntent] = []
        for intent in intents:
            price = data.states.get(intent.symbol).mid if intent.symbol in data.states else 0.0
            if price <= 0:
                continue
            notional = price * intent.qty
            if notional > self.max_order_notional:
                continue
            pos = positions.get(intent.symbol)
            pos_notional = abs((pos.qty if pos else 0.0) * price)
            if pos_notional + notional > self.max_pos_notional:
                continue
            filtered.append(intent)
        return filtered
