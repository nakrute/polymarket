from __future__ import annotations

import argparse
import csv
import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pandas as pd


BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"
RAW_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_asset_volume",
    "number_of_trades",
    "taker_buy_base_asset_volume",
    "taker_buy_quote_asset_volume",
    "ignore",
]


def month_range(start: str, end: str) -> list[str]:
    start_dt = datetime.strptime(start, "%Y-%m").replace(tzinfo=UTC)
    end_dt = datetime.strptime(end, "%Y-%m").replace(tzinfo=UTC)
    if end_dt < start_dt:
        raise SystemExit("--end must be the same as or after --start")

    months: list[str] = []
    current = start_dt
    while current <= end_dt:
        months.append(current.strftime("%Y-%m"))
        year = current.year + int(current.month == 12)
        month = 1 if current.month == 12 else current.month + 1
        current = current.replace(year=year, month=month)
    return months


def download_month(symbol: str, interval: str, month: str, timeout: int) -> pd.DataFrame | None:
    url = f"{BASE_URL}/{symbol}/{interval}/{symbol}-{interval}-{month}.zip"
    print(f"downloading {url}", flush=True)

    try:
        with urlopen(url, timeout=timeout) as response:
            payload = response.read()
    except HTTPError as error:
        if error.code == 404:
            print(f"missing {month}, skipping", flush=True)
            return None
        raise

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        csv_name = archive.namelist()[0]
        with archive.open(csv_name) as csv_file:
            text = io.TextIOWrapper(csv_file, encoding="utf-8")
            sample = text.readline()
            text.seek(0)
            has_header = sample.lower().startswith("open_time")
            frame = pd.read_csv(
                text,
                names=None if has_header else RAW_COLUMNS,
                header=0 if has_header else None,
                quoting=csv.QUOTE_MINIMAL,
            )

    frame = frame[["open_time", "open", "high", "low", "close", "volume"]].copy()
    open_time = pd.to_numeric(frame["open_time"], errors="raise")
    unit = "us" if open_time.max() > 10_000_000_000_000 else "ms"
    frame["timestamp"] = pd.to_datetime(open_time, unit=unit, utc=True)
    return frame[["timestamp", "open", "high", "low", "close", "volume"]]


def fetch_monthly(symbol: str, interval: str, start: str, end: str, timeout: int) -> pd.DataFrame:
    frames = []
    for month in month_range(start, end):
        frame = download_month(symbol, interval, month, timeout)
        if frame is not None:
            frames.append(frame)

    if not frames:
        raise SystemExit("No monthly files were downloaded")

    candles = pd.concat(frames, ignore_index=True)
    candles = candles.drop_duplicates("timestamp").sort_values("timestamp")
    return candles


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Binance Vision monthly kline archives.")
    parser.add_argument("--symbol", default="BTCUSDT", help="Archive symbol, e.g. BTCUSDT")
    parser.add_argument("--interval", default="5m", help="Kline interval, e.g. 5m")
    parser.add_argument("--start", required=True, help="Start month, YYYY-MM")
    parser.add_argument("--end", required=True, help="End month, YYYY-MM")
    parser.add_argument("--timeout", type=int, default=60, help="Download timeout in seconds")
    parser.add_argument("--output", default="data/btcusdt_5m.csv", help="Output CSV path")
    args = parser.parse_args()

    candles = fetch_monthly(args.symbol, args.interval, args.start, args.end, args.timeout)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    candles.to_csv(output, index=False)
    print(f"saved {len(candles)} candles to {output}", flush=True)


if __name__ == "__main__":
    main()
