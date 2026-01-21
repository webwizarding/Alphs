#!/usr/bin/env bash
set -euo pipefail

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

python -m src.main run --strategies pairs,mm,leadlag --symbols "${SYMBOLS:-SPY,QQQ,AAPL,MSFT,NVDA}"
