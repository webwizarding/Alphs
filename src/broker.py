from __future__ import annotations
import asyncio
from typing import Dict, List, Optional

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, ReplaceOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

from .utils.rate_limit import TokenBucket


class Broker:
    def __init__(self, api_key: str, api_secret: str, max_per_min: int = 60):
        self.client = TradingClient(api_key, api_secret, paper=True)
        rate_per_sec = max_per_min / 60.0
        self._bucket = TokenBucket(rate_per_sec=rate_per_sec, capacity=max_per_min)

    async def submit_limit(self, symbol: str, qty: float, side: OrderSide, limit_price: float, tif: TimeInForce, client_order_id: str):
        await self._bucket.acquire()
        req = LimitOrderRequest(symbol=symbol, qty=qty, side=side, limit_price=limit_price, time_in_force=tif, client_order_id=client_order_id)
        return self.client.submit_order(req)

    async def submit_market(self, symbol: str, qty: float, side: OrderSide, tif: TimeInForce, client_order_id: str):
        await self._bucket.acquire()
        req = MarketOrderRequest(symbol=symbol, qty=qty, side=side, time_in_force=tif, client_order_id=client_order_id)
        return self.client.submit_order(req)

    async def cancel(self, order_id: str) -> None:
        await self._bucket.acquire()
        self.client.cancel_order_by_id(order_id)

    async def replace(self, order_id: str, limit_price: Optional[float] = None, qty: Optional[float] = None):
        await self._bucket.acquire()
        req = ReplaceOrderRequest(limit_price=limit_price, qty=qty)
        return self.client.replace_order_by_id(order_id, req)

    async def cancel_all(self) -> None:
        await self._bucket.acquire()
        self.client.cancel_orders()

    async def list_positions(self):
        await self._bucket.acquire()
        return self.client.get_all_positions()

    async def get_account(self):
        await self._bucket.acquire()
        return self.client.get_account()

    async def list_orders(self, status: str = "open"):
        await self._bucket.acquire()
        return self.client.get_orders(status=status)
