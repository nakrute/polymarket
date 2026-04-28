from __future__ import annotations

import argparse
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd


def _load_ccxt():
    try:
        import ccxt
    except ImportError as error:
        raise SystemExit(
            "ccxt is not installed. Run: pip install -r requirements.txt"
        ) from error
    return ccxt


def fetch_ohlcv(
    exchange_name: str,
    symbol: str,
    timeframe: str,
    since: datetime,
    limit: int,
    timeout_ms: int,
) -> pd.DataFrame:
    ccxt = _load_ccxt()
    exchange_class = getattr(ccxt, exchange_name, None)
    if exchange_class is None:
        raise SystemExit(f"Unknown ccxt exchange: {exchange_name}")

    print(f"connecting to {exchange_name}...", flush=True)
    exchange = exchange_class({"enableRateLimit": True, "timeout": timeout_ms})
    print("loading markets...", flush=True)
    exchange.load_markets()
    if symbol not in exchange.markets:
        examples = ", ".join(list(exchange.markets)[:10])
        raise SystemExit(
            f"{symbol} is not available on {exchange_name}. "
            f"First available symbols include: {examples}"
        )

    since_ms = int(since.timestamp() * 1000)
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    rows: list[list[float]] = []
    request_count = 0

    print(
        f"fetching {symbol} {timeframe} candles since {since.isoformat()}...",
        flush=True,
    )
    while since_ms < now_ms:
        request_count += 1
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=limit)
        if not batch:
            print("exchange returned no more candles", flush=True)
            break

        rows.extend(batch)
        newest_ms = int(batch[-1][0])
        newest_time = datetime.fromtimestamp(newest_ms / 1000, UTC)
        print(
            f"batch {request_count}: got {len(batch)} candles "
            f"through {newest_time.isoformat()} total={len(rows)}",
            flush=True,
        )
        next_since_ms = newest_ms + 1
        if next_since_ms <= since_ms:
            break
        since_ms = next_since_ms

        if getattr(exchange, "rateLimit", None):
            time.sleep(exchange.rateLimit / 1000)

    frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    if frame.empty:
        raise SystemExit("No candles returned")

    frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    frame = frame.drop_duplicates("timestamp").sort_values("timestamp")
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch BTC OHLCV candles to CSV.")
    parser.add_argument("--exchange", default="kraken", help="ccxt exchange id, e.g. kraken")
    parser.add_argument("--symbol", default="BTC/USD", help="Exchange market symbol")
    parser.add_argument("--timeframe", default="5m", help="Candle timeframe")
    parser.add_argument("--days", type=int, default=30, help="Number of recent days to fetch")
    parser.add_argument("--limit", type=int, default=720, help="Candles per exchange request")
    parser.add_argument("--timeout-ms", type=int, default=30_000, help="Exchange request timeout")
    parser.add_argument("--output", default="data/btc_usd_5m.csv", help="Output CSV path")
    args = parser.parse_args()

    since = datetime.now(UTC) - timedelta(days=args.days)
    candles = fetch_ohlcv(
        args.exchange,
        args.symbol,
        args.timeframe,
        since,
        args.limit,
        args.timeout_ms,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    candles.to_csv(output, index=False)
    print(f"saved {len(candles)} candles to {output}")


if __name__ == "__main__":
    main()
