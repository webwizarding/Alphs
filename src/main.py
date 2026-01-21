from __future__ import annotations
import argparse
import asyncio
import os
import signal
import sys
import time
from typing import Dict, List

from alpaca.trading.enums import OrderSide, TimeInForce

from .config import load_config, parse_args
from .data_stream import MarketDataStream
from .trade_stream import TradeStream
from .broker import Broker
from .execution import ExecutionEngine, OrderIntent
from .risk import RiskManager, PositionState
from .metrics import Metrics
from .utils.alerts import DiscordAlerter
from .strategies.pairs_stat_arb import PairsStatArb
from .strategies.avellaneda_stoikov_mm import AvellanedaStoikovMM
from .strategies.lead_lag_arb import LeadLagArb
from .strategies.etf_basket_arb import ETFBasketArb
from .strategies.news_event_driven import NewsEventDriven
from .strategies.ml_orderflow import MLOrderflow
from .utils.scheduler import AsyncScheduler
from .utils.time import now_eastern, is_regular_hours, seconds_to_close


async def run_trader(args: argparse.Namespace) -> None:
    cfg = load_config(args)

    broker = Broker(cfg.api_key_id, cfg.api_secret_key, cfg.paper_rest, max_per_min=cfg.risk.max_trades_per_min)
    data_stream = MarketDataStream(cfg.api_key_id, cfg.api_secret_key, cfg.symbols, feed=cfg.feed)
    trade_stream = TradeStream(cfg.api_key_id, cfg.api_secret_key, cfg.paper_rest)
    execution = ExecutionEngine(broker, max_open_orders=cfg.risk.max_open_orders)
    risk = RiskManager(cfg.risk.max_gross_exposure_usd, cfg.risk.max_net_exposure_usd, cfg.risk.max_order_notional_usd, cfg.risk.max_position_notional_usd, cfg.risk.daily_loss_limit_usd)
    metrics = Metrics(cfg.log_dir)
    alerter = DiscordAlerter(cfg.discord_webhook_url)
    news_stream = None

    positions: Dict[str, PositionState] = {}

    last_pos_ts = 0.0
    last_acct_ts = 0.0

    async def refresh_positions(force: bool = False) -> None:
        nonlocal positions
        nonlocal last_pos_ts
        now = time.time()
        if not force and now - last_pos_ts < 10:
            return
        pos_list = await broker.list_positions()
        positions = {p.symbol: PositionState(symbol=p.symbol, qty=float(p.qty), avg_price=float(p.avg_entry_price)) for p in pos_list}
        last_pos_ts = now

    async def refresh_account() -> None:
        nonlocal last_acct_ts
        now = time.time()
        if now - last_acct_ts < 10:
            return
        acct = await broker.get_account()
        risk.update_account(float(acct.equity))
        last_acct_ts = now

    disabled_strats = set()
    reject_counts: Dict[str, int] = {}
    filled_tracker: Dict[str, float] = {}

    async def handle_trade_update(update: dict) -> None:
        order = update.get("order", {})
        event = update.get("event")
        client_id = order.get("client_order_id", "")
        strategy = client_id.split(":")[0] if ":" in client_id else "unknown"
        if event == "rejected":
            reject_counts[strategy] = reject_counts.get(strategy, 0) + 1
            if reject_counts[strategy] >= 5:
                disabled_strats.add(strategy)
                await alerter.send("strategy_disabled", f"{strategy} disabled after repeated rejects")
        if event in {"fill", "partial_fill"}:
            symbol = order.get("symbol")
            side = order.get("side")
            order_id = order.get("id")
            filled_qty = float(order.get("filled_qty", 0))
            last_qty = filled_tracker.get(order_id, 0.0)
            delta_qty = max(0.0, filled_qty - last_qty)
            filled_tracker[order_id] = filled_qty
            if delta_qty <= 0:
                delta_qty = 0.0
            price = float(order.get("filled_avg_price") or order.get("filled_avg_price", 0) or 0)
            st = data_stream.states.get(symbol)
            mid = st.mid if st else None
            if delta_qty > 0:
                metrics.record_fill(strategy, symbol, delta_qty, price, side, mid=mid)
        await execution.on_trade_update(update)

    trade_stream.add_handler(handle_trade_update)

    strategies = []
    if cfg.strategies.pairs:
        strategies.append(PairsStatArb(cfg.pairs))
    if cfg.strategies.mm:
        strategies.append(AvellanedaStoikovMM(cfg.symbols))
    if cfg.strategies.leadlag:
        strategies.append(LeadLagArb(cfg.leader_symbol, cfg.lead_lag_symbols))
    if cfg.strategies.etf:
        strategies.append(ETFBasketArb(cfg.etf_pairs, cfg.etf_baskets))
    news_strategy = None
    if cfg.strategies.news:
        news_strategy = NewsEventDriven(cfg.symbols)
        strategies.append(news_strategy)
    if cfg.strategies.ml:
        strategies.append(MLOrderflow(cfg.symbols))

    async def tick() -> None:
        if cfg.session.trade_only_regular_hours:
            ts = now_eastern()
            if not is_regular_hours(ts):
                return
            if seconds_to_close(ts) < cfg.session.flatten_before_close_minutes * 60:
                await flatten_all()
                return
        await refresh_account()
        await refresh_positions()
        gross = 0.0
        net = 0.0
        for sym, pos in positions.items():
            st = data_stream.states.get(sym)
            price = st.mid if st and st.mid > 0 else pos.avg_price
            notional = pos.qty * price
            gross += abs(notional)
            net += notional
        metrics.log_event("exposure", {"gross": gross, "net": net})
        intents: List[OrderIntent] = []
        for strat in strategies:
            if strat.name in disabled_strats:
                continue
            intents.extend(strat.on_tick(data_stream, positions))
        intents = risk.check(intents, positions, data_stream)
        if risk.kill_switch:
            await alerter.send("kill_switch", "daily loss limit reached, flattening positions")
            await flatten_all()
            return
        await execution.sync(intents)

    async def flatten_all() -> None:
        await refresh_positions(force=True)
        intents: List[OrderIntent] = []
        for sym, pos in positions.items():
            if pos.qty == 0:
                continue
            st = data_stream.states.get(sym)
            price = st.mid if st and st.mid > 0 else pos.avg_price
            side = OrderSide.SELL if pos.qty > 0 else OrderSide.BUY
            intents.append(OrderIntent(symbol=sym, side=side, qty=abs(pos.qty), limit_price=price, tif=TimeInForce.DAY, strategy="flatten", intent_id=f"{sym}-flat", order_type="market"))
        await execution.sync(intents)

    await data_stream.start()
    await trade_stream.start()
    await alerter.send("startup", "trader started")
    if news_strategy:
        try:
            from alpaca.data.live import NewsDataStream

            news_stream = NewsDataStream(cfg.api_key_id, cfg.api_secret_key)

            async def _on_news(n) -> None:
                symbol = n.symbols[0] if getattr(n, "symbols", None) else ""
                headline = n.headline if hasattr(n, "headline") else ""
                if symbol and headline:
                    news_strategy.on_news(symbol, headline)

            news_stream.subscribe_news(_on_news, *cfg.symbols)
            asyncio.create_task(news_stream.run())
        except Exception:
            metrics.log_event("news_stream", {"status": "unavailable"})
            await alerter.send("news_stream", "news stream unavailable")

    scheduler = AsyncScheduler(cfg.tick_interval_sec)
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _stop(*_args) -> None:
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _stop)

    tick_task = asyncio.create_task(scheduler.start(tick))
    await stop_event.wait()
    scheduler.stop()
    await tick_task
    if cfg.session.cancel_all_on_shutdown:
        await broker.cancel_all()
    await flatten_all()
    await alerter.send("shutdown", "trader stopped")
    await trade_stream.stop()
    await data_stream.stop()
    if news_stream:
        await news_stream.stop_ws()
    metrics.write_summary()


async def status_cmd(args: argparse.Namespace) -> None:
    cfg = load_config(args)
    broker = Broker(cfg.api_key_id, cfg.api_secret_key, cfg.paper_rest, max_per_min=cfg.risk.max_trades_per_min)
    acct = await broker.get_account()
    positions = await broker.list_positions()
    print(f"equity={acct.equity} cash={acct.cash} buying_power={acct.buying_power}")
    for p in positions:
        print(f"{p.symbol} qty={p.qty} avg={p.avg_entry_price} unrealized_pl={p.unrealized_pl}")


async def flatten_cmd(args: argparse.Namespace) -> None:
    cfg = load_config(args)
    broker = Broker(cfg.api_key_id, cfg.api_secret_key, cfg.paper_rest, max_per_min=cfg.risk.max_trades_per_min)
    positions = await broker.list_positions()
    for p in positions:
        qty = abs(float(p.qty))
        if qty == 0:
            continue
        side = OrderSide.SELL if float(p.qty) > 0 else OrderSide.BUY
        await broker.submit_market(p.symbol, qty, side, TimeInForce.DAY, f"flatten-{p.symbol}-{int(time.time())}")


async def backtest_pairs_cmd(args: argparse.Namespace) -> None:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    import datetime as dt

    cfg = load_config(args)
    pairs = [p.strip() for p in (args.pairs or ",".join(cfg.pairs)).split(",") if p.strip()]
    if not pairs:
        print("no pairs")
        return
    client = StockHistoricalDataClient(cfg.api_key_id, cfg.api_secret_key)
    end = now_eastern()
    start = end - dt.timedelta(days=args.days)
    for pair in pairs:
        s1, s2 = pair.split("/")
        req = StockBarsRequest(symbol_or_symbols=[s1, s2], timeframe=TimeFrame.Minute, start=start, end=end)
        barset = client.get_stock_bars(req)
        data = barset.data
        s1_bars = data.get(s1, [])[-3:]
        s2_bars = data.get(s2, [])[-3:]
        print(pair, {"s1": s1_bars, "s2": s2_bars})


def main() -> None:
    args = parse_args()
    if args.cmd == "run":
        asyncio.run(run_trader(args))
    elif args.cmd == "status":
        asyncio.run(status_cmd(args))
    elif args.cmd == "flatten":
        asyncio.run(flatten_cmd(args))
    elif args.cmd == "backtest_pairs":
        asyncio.run(backtest_pairs_cmd(args))


if __name__ == "__main__":
    main()
