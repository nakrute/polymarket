# BTC 5-Minute Trading Bot

A defensive starter bot for BTC 5-minute trading research. The first version is built for paper trading and backtesting, with shared strategy code between both paths.

## What It Does

- Loads OHLCV candles from CSV for backtests.
- Runs a 5-minute trend strategy with 1-hour regime confirmation.
- Sizes trades by account risk and ATR distance.
- Simulates fees, stop exits, signal exits, and max holding time.
- Provides a paper-trading loop scaffold for later exchange integration.

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m btc_bot.backtest --csv data/sample_btc_5m.csv
```

The sample CSV is intentionally tiny and only proves the plumbing. Use real 5-minute BTC data before trusting any backtest result.

## Fetch Real BTC Candles

After installing requirements:

```powershell
python -m btc_bot.fetch_data --exchange kraken --symbol BTC/USD --timeframe 5m --days 90 --output data/btc_usd_5m.csv
python -m btc_bot.backtest --csv data/btc_usd_5m.csv
```

Notes:

- Kraken uses `BTC/USD`.
- Binance-style venues often use `BTC/USDT`.
- Fetched CSVs in `data/` are ignored by Git except for the tiny sample file.

## CSV Format

Expected columns:

```text
timestamp,open,high,low,close,volume
```

`timestamp` should be parseable by pandas, ideally UTC ISO-8601.

## Project Layout

```text
btc_bot/
  backtest.py       Backtest runner
  config.py         Strategy, risk, and execution settings
  data.py           Candle loading and validation
  exchange.py       Paper/live exchange interfaces
  indicators.py     EMA, RSI, ATR helpers
  risk.py           Position sizing and risk state
  strategy.py       Shared trading signal logic
  trader.py         Paper trading loop scaffold
```

## Safety Defaults

This project starts in paper mode. Before adding real orders:

- Confirm exchange balances and open positions on every loop.
- Use API keys with restricted permissions.
- Add a hard kill switch.
- Start with tiny size.
- Compare the bot against simply holding BTC.

Nothing here is financial advice.
