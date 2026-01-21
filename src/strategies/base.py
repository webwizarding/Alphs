from __future__ import annotations
from typing import Dict, List

from alpaca.trading.enums import OrderSide, TimeInForce

from ..execution import OrderIntent
from ..risk import PositionState
from ..data_stream import MarketDataStream


class Strategy:
    name = ""

    def __init__(self, symbols: List[str]):
        self.symbols = symbols

    def on_tick(self, data: MarketDataStream, positions: Dict[str, PositionState]) -> List[OrderIntent]:
        return []

    def _mk_intent(self, symbol: str, side: OrderSide, qty: float, limit_price: float | None, tif: TimeInForce, intent_id: str, order_type: str = "limit") -> OrderIntent:
        return OrderIntent(
            symbol=symbol,
            side=side,
            qty=qty,
            limit_price=limit_price,
            tif=tif,
            strategy=self.name,
            intent_id=intent_id,
            order_type=order_type,
        )
