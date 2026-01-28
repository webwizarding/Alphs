from __future__ import annotations
import argparse
import os
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class RiskConfig:
    max_gross_exposure_usd: float = 25000.0
    max_net_exposure_usd: float = 10000.0
    max_order_notional_usd: float = 2000.0
    max_position_notional_usd: float = 5000.0
    max_open_orders: int = 50
    daily_loss_limit_usd: float = 250.0
    max_trades_per_min: int = 30


@dataclass
class SessionConfig:
    trade_only_regular_hours: bool = True
    flatten_before_close_minutes: int = 10
    cancel_all_on_shutdown: bool = True


@dataclass
class StrategyToggles:
    pairs: bool = False
    mm: bool = False
    leadlag: bool = False
    etf: bool = False
    news: bool = False
    ml: bool = False


@dataclass
class AppConfig:
    api_key_id: str
    api_secret_key: str
    paper_rest: str = "https://paper-api.alpaca.markets/v2"
    feed: str = "iex"
    symbols: List[str] = field(default_factory=list)
    pairs: List[str] = field(default_factory=list)
    leader_symbol: str = "SPY"
    lead_lag_symbols: List[str] = field(default_factory=list)
    etf_pairs: List[str] = field(default_factory=list)
    etf_baskets: Dict[str, str] = field(default_factory=dict)
    tick_interval_sec: float = 1.0
    bars_timeframe: str = "1Min"
    subscribe_bars: bool = True
    subscribe_trades: bool = True
    max_stream_symbols: int = 50
    max_stream_subscriptions: int = 30
    log_dir: str = "logs"
    discord_webhook_url: str = ""
    risk: RiskConfig = field(default_factory=RiskConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    strategies: StrategyToggles = field(default_factory=StrategyToggles)
    strategy_params: Dict[str, str] = field(default_factory=dict)


def env_default(name: str, default: str) -> str:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y"}


def env_list(name: str, default: str) -> List[str]:
    raw = os.environ.get(name, default)
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("\"").strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="alpaca-hft")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run")
    run.add_argument("--strategies", default="")
    run.add_argument("--symbols", default="")
    run.add_argument("--tick", type=float, default=None)
    run.add_argument("--paper", action="store_true")

    sub.add_parser("status")
    sub.add_parser("flatten")

    backtest = sub.add_parser("backtest_pairs")
    backtest.add_argument("--pairs", default="")
    backtest.add_argument("--days", type=int, default=7)

    return p.parse_args()


def load_config(args: argparse.Namespace) -> AppConfig:
    load_dotenv()
    api_key_id = env_default("ALPACA_API_KEY_ID", "")
    api_secret_key = env_default("ALPACA_API_SECRET_KEY", "")
    if args.cmd == "run" and (not api_key_id or not api_secret_key):
        raise RuntimeError("Missing ALPACA_API_KEY_ID/ALPACA_API_SECRET_KEY")

    symbols = env_list("SYMBOLS", "SPY,QQQ,AAPL,MSFT,AMZN,META,NVDA")
    if args.cmd == "run" and args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    pairs = env_list("PAIRS", "KO/PEP,XOM/CVX")
    lead_lag_symbols = env_list("LEAD_LAG_SYMBOLS", "AAPL,MSFT,NVDA,AMZN")
    etf_pairs = env_list("ETF_PAIRS", "SPY/IVV,QQQ/QQQM")
    baskets_raw = env_default("ETF_BASKETS", "")
    baskets: Dict[str, str] = {}
    if baskets_raw:
        for item in baskets_raw.split(";"):
            if not item.strip():
                continue
            key, value = item.split("=")
            baskets[key.strip().upper()] = value.strip()

    strat_flags = StrategyToggles(
        pairs=env_bool("STRAT_PAIRS", False),
        mm=env_bool("STRAT_MM", False),
        leadlag=env_bool("STRAT_LEADLAG", False),
        etf=env_bool("STRAT_ETF", False),
        news=env_bool("STRAT_NEWS", False),
        ml=env_bool("STRAT_ML", False),
    )

    if args.cmd == "run" and args.strategies:
        names = {s.strip().lower() for s in args.strategies.split(",") if s.strip()}
        strat_flags = StrategyToggles(
            pairs="pairs" in names,
            mm="mm" in names,
            leadlag="leadlag" in names,
            etf="etf" in names,
            news="news" in names,
            ml="ml" in names,
        )

    tick_interval_sec = float(env_default("TICK_INTERVAL_SEC", "1.0"))
    if args.cmd == "run" and args.tick is not None:
        tick_interval_sec = args.tick

    paper_rest = env_default("ALPACA_PAPER_REST", "https://paper-api.alpaca.markets/v2")
    if paper_rest.endswith("/v2"):
        paper_rest = paper_rest[:-3]

    feed = env_default("FEED", "iex").lower()
    if feed != "iex":
        feed = "iex"

    cfg = AppConfig(
        api_key_id=api_key_id,
        api_secret_key=api_secret_key,
        paper_rest=paper_rest,
        feed=feed,
        symbols=symbols,
        pairs=pairs,
        leader_symbol=env_default("LEAD_LAG_LEADER", "SPY").upper(),
        lead_lag_symbols=lead_lag_symbols,
        etf_pairs=etf_pairs,
        etf_baskets=baskets,
        tick_interval_sec=tick_interval_sec,
        bars_timeframe=env_default("BARS_TIMEFRAME", "1Min"),
        subscribe_bars=env_bool("SUBSCRIBE_BARS", True),
        subscribe_trades=env_bool("SUBSCRIBE_TRADES", True),
        max_stream_symbols=int(env_default("MAX_STREAM_SYMBOLS", "50")),
        max_stream_subscriptions=int(env_default("MAX_STREAM_SUBSCRIPTIONS", "30")),
        log_dir=env_default("LOG_DIR", "logs"),
        discord_webhook_url=env_default("DISCORD_WEBHOOK_URL", ""),
        risk=RiskConfig(
            max_gross_exposure_usd=float(env_default("MAX_GROSS_EXPOSURE_USD", "25000")),
            max_net_exposure_usd=float(env_default("MAX_NET_EXPOSURE_USD", "10000")),
            max_order_notional_usd=float(env_default("MAX_ORDER_NOTIONAL_USD", "2000")),
            max_position_notional_usd=float(env_default("MAX_POSITION_NOTIONAL_USD", "5000")),
            max_open_orders=int(env_default("MAX_OPEN_ORDERS", "50")),
            daily_loss_limit_usd=float(env_default("DAILY_LOSS_LIMIT_USD", "250")),
            max_trades_per_min=int(env_default("MAX_TRADES_PER_MIN", "30")),
        ),
        session=SessionConfig(
            trade_only_regular_hours=env_bool("TRADE_ONLY_REGULAR_HOURS", True),
            flatten_before_close_minutes=int(env_default("FLATTEN_BEFORE_CLOSE_MINUTES", "10")),
            cancel_all_on_shutdown=env_bool("CANCEL_ALL_ON_SHUTDOWN", True),
        ),
        strategies=strat_flags,
        strategy_params={},
    )
    return cfg
