# Bur

## Installation

Step 1: Install prerequisites

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip
```

Step 2: Create and activate a virtual environment

```bash
python3.12 -m venv .venv
. ./.venv/bin/activate
set -a; . ./.env; set +a
```

Step 3: Install dependencies

```bash
pip install -U pip
pip install -e .
```

Step 4: Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your Alpaca paper credentials and preferred symbols/limits before running.
Run commands use symbols from `.env` by default.
Set `DISCORD_WEBHOOK_URL` to enable Discord alerts.
If you hit a symbol limit error, reduce `SYMBOLS`/`PAIRS`/`LEAD_LAG_SYMBOLS` or set `SUBSCRIBE_BARS=false` and `SUBSCRIBE_TRADES=false`. You can also set `MAX_STREAM_SUBSCRIPTIONS` (default 30) to enforce a hard cap across quote/trade/bar channels.

Step 5: Run once in the foreground

```bash
python -m src.main run --strategies pairs,mm,leadlag
```

Step 6: Install and start the systemd service (runs without your SSH session)

```bash
sudo cp scripts/systemd/alpaca_hft_paper.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable alpaca_hft_paper.service
sudo systemctl start alpaca_hft_paper.service
```

Step 7: Check status and logs

```bash
sudo systemctl status alpaca_hft_paper.service
sudo journalctl -u alpaca_hft_paper.service -f
```

Step 8: Optional market-hours timers (start at 09:25 ET, stop at 16:05 ET)

```bash
sudo cp scripts/systemd/alpaca_hft_paper_start.service /etc/systemd/system/
sudo cp scripts/systemd/alpaca_hft_paper_stop.service /etc/systemd/system/
sudo cp scripts/systemd/alpaca_hft_paper_start.timer /etc/systemd/system/
sudo cp scripts/systemd/alpaca_hft_paper_stop.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now alpaca_hft_paper_start.timer
sudo systemctl enable --now alpaca_hft_paper_stop.timer
```

Optional uvloop:

```bash
pip install -e ".[uvloop]"
```

## Runtime commands

Status:

```bash
python -m src.main status
```

Flatten:

```bash
python -m src.main flatten
```

Service management:

```bash
sudo systemctl stop alpaca_hft_paper.service
sudo systemctl restart alpaca_hft_paper.service
sudo systemctl disable alpaca_hft_paper.service
sudo rm /etc/systemd/system/alpaca_hft_paper.service
sudo systemctl daemon-reload
```

Note: The app already respects `TRADE_ONLY_REGULAR_HOURS=true` and will idle outside market hours even if the service stays running.

## Strategies

- pairs: short-term statistical arbitrage
- mm: Avellaneda–Stoikov-inspired market making
- leadlag: cross-asset lead–lag
- etf: ETF/ETF and ETF/basket mean reversion
- news: event-driven stub (off by default)
- ml: lightweight online order-flow model

## Metrics

- JSONL events: `logs/events.jsonl`
- CSV summary: `logs/daily_summary.csv`
- Discord alerts: startup, shutdown, kill switch, strategy disable, news stream unavailable

## Safety / Reality check

- This is not institutional HFT. True latency arb and professional market making require colocation, direct feeds, and specialized infrastructure beyond a VPS and IEX.
- Paper fills are simulated from real-time quotes and do not model queue position, slippage, or fees accurately.
- Treat results as research and learning only, not live performance indicators.

## Notes

- Alpaca paper base REST endpoint is normalized to remove `/v2` if present.
- One market-data websocket connection is used for quotes/trades/bars.
- Trade updates are consumed via the paper `trade_updates` stream.
