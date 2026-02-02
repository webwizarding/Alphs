## Installation

Step 1: Install prerequisites

```bash
sudo apt update
sudo apt install -y python3 python3-pip
```

Step 2: Install deps

```bash
sudo pip3 install -U pip
sudo pip3 install -e /home/Alphs
```

Step 3: Configs

```bash
cp .env.example .env
```

Edit `.env` with your Alpaca paper credentials and preferred symbols/limits before running.
Run commands use symbols from `.env` by default.
Set `DISCORD_WEBHOOK_URL` to enable Discord alerts.
If you hit a symbol limit error, reduce `SYMBOLS`/`PAIRS`/`LEAD_LAG_SYMBOLS` or set `SUBSCRIBE_BARS=false` and `SUBSCRIBE_TRADES=false`. You can also set `MAX_STREAM_SUBSCRIPTIONS` (default 30) to enforce a hard cap across quote/trade/bar channels.
- Alpaca paper base REST endpoint is normalized to remove `/v2` if present.
- One market-data websocket connection is used for quotes/trades/bars.
- Trade updates are consumed via the paper `trade_updates` stream.

Step 4: Run once 

```bash
python3 -m src.main run --strategies pairs,mm,leadlag
```

Step 5: Install and start the systemd service 

```bash
sudo cp scripts/systemd/alpaca_hft_paper.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable alpaca_hft_paper.service
sudo systemctl start alpaca_hft_paper.service
```

Step 6: Check status and logs

```bash
sudo systemctl status alpaca_hft_paper.service
sudo journalctl -u alpaca_hft_paper.service -f
```

## Runtime commands

Status:

```bash
python3 -m src.main status
```

Flatten:

```bash
python3 -m src.main flatten
```

Service management cmds:

```bash
sudo systemctl stop alpaca_hft_paper.service
sudo systemctl restart alpaca_hft_paper.service
sudo systemctl disable alpaca_hft_paper.service
sudo rm /etc/systemd/system/alpaca_hft_paper.service
sudo systemctl daemon-reload
```

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

