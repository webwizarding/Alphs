from __future__ import annotations
import csv
import json
import os
import time
from dataclasses import dataclass
from typing import Dict


@dataclass
class StratStats:
    trades: int = 0
    wins: int = 0
    losses: int = 0
    pnl: float = 0.0
    turnover: float = 0.0
    max_drawdown: float = 0.0
    peak_pnl: float = 0.0
    slippage: float = 0.0
    fills: int = 0


class Metrics:
    def __init__(self, log_dir: str):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.json_path = os.path.join(log_dir, "events.jsonl")
        self.csv_path = os.path.join(log_dir, "daily_summary.csv")
        self.stats: Dict[str, StratStats] = {}
        self.positions: Dict[str, Dict[str, float]] = {}
        self.avg_cost: Dict[str, Dict[str, float]] = {}

    def log_event(self, event: str, payload: dict) -> None:
        record = {"ts": time.time(), "event": event, **payload}
        with open(self.json_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def record_fill(self, strategy: str, symbol: str, qty: float, price: float, side: str, mid: float | None = None) -> None:
        stats = self.stats.setdefault(strategy, StratStats())
        stats.trades += 1
        stats.turnover += abs(qty * price)
        stats.fills += 1
        if mid is not None and mid > 0:
            if side == "buy":
                stats.slippage += price - mid
            else:
                stats.slippage += mid - price

        pos = self.positions.setdefault(strategy, {}).get(symbol, 0.0)
        avg = self.avg_cost.setdefault(strategy, {}).get(symbol, 0.0)
        new_pos = pos + qty if side == "buy" else pos - qty

        realized = 0.0
        if pos == 0.0:
            avg = price
        elif (pos > 0 and side == "sell") or (pos < 0 and side == "buy"):
            realized = (price - avg) * qty if pos > 0 else (avg - price) * qty
        else:
            avg = (avg * abs(pos) + price * qty) / (abs(pos) + qty)

        self.positions[strategy][symbol] = new_pos
        self.avg_cost[strategy][symbol] = avg

        stats.pnl += realized
        if realized >= 0:
            stats.wins += 1
        else:
            stats.losses += 1
        stats.peak_pnl = max(stats.peak_pnl, stats.pnl)
        stats.max_drawdown = min(stats.max_drawdown, stats.pnl - stats.peak_pnl)

    def write_summary(self) -> None:
        fields = ["strategy", "trades", "fills", "wins", "losses", "win_rate", "pnl", "turnover", "max_drawdown", "avg_slippage"]
        write_header = not os.path.exists(self.csv_path)
        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            if write_header:
                w.writeheader()
            for name, stats in self.stats.items():
                w.writerow({
                    "strategy": name,
                    "trades": stats.trades,
                    "fills": stats.fills,
                    "wins": stats.wins,
                    "losses": stats.losses,
                    "win_rate": round((stats.wins / stats.trades) if stats.trades else 0.0, 4),
                    "pnl": round(stats.pnl, 2),
                    "turnover": round(stats.turnover, 2),
                    "max_drawdown": round(stats.max_drawdown, 2),
                    "avg_slippage": round((stats.slippage / stats.fills) if stats.fills else 0.0, 6),
                })
