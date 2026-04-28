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

The default strategy uses a 200-period hourly regime EMA, so it needs at least 9 days of data before it can take trades. For a quick smoke test on a smaller file:

```powershell
python -m btc_bot.backtest --csv data/btc_usd_5m.csv --regime-ema 20 --diagnostics
```

If the fetch command appears stuck, it should now print each step. A quick smoke test is:

```powershell
python -m btc_bot.fetch_data --exchange kraken --symbol BTC/USD --timeframe 5m --days 1 --output data/btc_usd_5m.csv
```

Notes:

- Kraken uses `BTC/USD`.
- Binance-style venues often use `BTC/USDT`.
- Fetched CSVs in `data/` are ignored by Git except for the tiny sample file.

## Fetch Deeper Binance Archive Data

Kraken and other exchange APIs can be shallow. For deeper 5-minute spot history, use Binance's public monthly archive files:

```powershell
python -m btc_bot.fetch_binance_vision --symbol BTCUSDT --interval 5m --start 2024-01 --end 2024-12 --output data/btcusdt_5m_2024.csv
python -m btc_bot.backtest --csv data/btcusdt_5m_2024.csv --diagnostics
```

This archive uses `BTCUSDT`, so it is best treated as BTC/USDT research data rather than exact BTC/USD execution data.

## Try A More Active Research Pass

The default strategy is intentionally defensive and may trade rarely. To test whether the idea has more signal with looser gates:

```powershell
python -m btc_bot.backtest --csv data/btcusdt_5m_2024.csv --regime-ema 50 --fast-ema 10 --slow-ema 30 --min-rsi 48 --max-rsi 80 --volume-window 1 --max-holding-bars 72 --diagnostics
```

The strongest 2024 research pass so far uses 15-minute signals, a 4-hour regime, pullback entries, ATR expansion, and lower maker-style costs:

```powershell
python -m btc_bot.backtest --csv data/btcusdt_5m_2024.csv --signal-timeframe 15min --regime-timeframe 4h --regime-ema 50 --fast-ema 10 --slow-ema 30 --min-rsi 48 --max-rsi 80 --volume-window 1 --max-holding-bars 144 --max-losses 999 --entry-mode pullback --min-atr-expansion 1.05 --fee-hurdle-multiple 2 --fee-rate 0.0002 --slippage-bps 0.5 --trades-output data/trades_15m_4h_pullback_maker_2024.csv --diagnostics
```

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
