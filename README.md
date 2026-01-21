# Alpaca HFT Paper Forward-Tester

Forward-test multiple HFT-style strategy families on Alpaca paper trading using IEX data. Designed for a modest VPS with conservative defaults.

## Install

```bash
python3.12 -m venv .venv
. ./.venv/bin/activate
pip install -U pip
pip install -e .
```

Optional uvloop:

```bash
pip install -e ".[uvloop]"
```

## Configure

```bash
cp .env.example .env
```

Edit `.env` with your Alpaca paper credentials and preferred symbols/limits.

## Run

```bash
. ./.venv/bin/activate
python -m src.main run --strategies pairs,mm,leadlag --symbols "SPY,QQQ,AAPL,MSFT,NVDA"
```

Status:

```bash
python -m src.main status
```

Flatten:

```bash
python -m src.main flatten
```

## Scripts

```bash
bash scripts/run_paper.sh
```

Systemd example:

`scripts/systemd/alpaca_hft_paper.service`

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

## Safety / Reality check

- This is not institutional HFT. True latency arb and professional market making require colocation, direct feeds, and specialized infrastructure beyond a VPS and IEX.
- Paper fills are simulated from real-time quotes and do not model queue position, slippage, or fees accurately.
- Treat results as research and learning only, not live performance indicators.

## Notes

- Alpaca paper base REST endpoint is normalized to remove `/v2` if present.
- One market-data websocket connection is used for quotes/trades/bars.
- Trade updates are consumed via the paper `trade_updates` stream.
