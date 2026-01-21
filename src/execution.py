from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from alpaca.trading.enums import OrderSide, TimeInForce

from .broker import Broker


@dataclass
class OrderIntent:
    symbol: str
    side: OrderSide
    qty: float
    limit_price: Optional[float]
    tif: TimeInForce
    strategy: str
    intent_id: str
    order_type: str = "limit"


class ExecutionEngine:
    def __init__(self, broker: Broker, max_open_orders: int = 50):
        self.broker = broker
        self.max_open_orders = max_open_orders
        self.open_orders: Dict[str, dict] = {}

    def _client_id(self, intent: OrderIntent) -> str:
        return f"{intent.strategy}:{intent.intent_id}:{intent.symbol}:{intent.side.value}"

    async def sync(self, intents: List[OrderIntent]) -> None:
        desired_ids = set()
        for intent in intents:
            client_id = self._client_id(intent)
            desired_ids.add(client_id)
            if client_id in self.open_orders:
                existing = self.open_orders[client_id]
                if intent.limit_price and existing.get("limit_price") != intent.limit_price:
                    await self._cancel(client_id, existing)
                    await self._submit(intent, client_id)
                continue
            if len(self.open_orders) >= self.max_open_orders:
                continue
            await self._submit(intent, client_id)
        await self._cancel_stale(desired_ids)

    async def _submit(self, intent: OrderIntent, client_id: str) -> None:
        if intent.order_type == "market":
            order = await self.broker.submit_market(intent.symbol, intent.qty, intent.side, intent.tif, client_id)
        else:
            if intent.limit_price is None:
                return
            order = await self.broker.submit_limit(intent.symbol, intent.qty, intent.side, intent.limit_price, intent.tif, client_id)
        self.open_orders[client_id] = {
            "order_id": order.id,
            "symbol": intent.symbol,
            "side": intent.side.value,
            "qty": float(intent.qty),
            "limit_price": float(intent.limit_price) if intent.limit_price else None,
            "strategy": intent.strategy,
            "ts": time.time(),
        }

    async def _cancel(self, client_id: str, existing: dict) -> None:
        order_id = existing.get("order_id")
        if not order_id:
            return
        await self.broker.cancel(order_id)
        self.open_orders.pop(client_id, None)

    async def _cancel_stale(self, desired_ids: set) -> None:
        for client_id, existing in list(self.open_orders.items()):
            if client_id not in desired_ids:
                await self._cancel(client_id, existing)

    async def on_trade_update(self, update: dict) -> None:
        order = update.get("order", {})
        client_id = order.get("client_order_id")
        if not client_id:
            return
        event = update.get("event")
        if event in {"fill", "partial_fill", "canceled", "rejected", "expired"}:
            if event in {"canceled", "rejected", "expired"}:
                self.open_orders.pop(client_id, None)
        if event == "fill":
            self.open_orders.pop(client_id, None)
