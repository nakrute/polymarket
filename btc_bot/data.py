from __future__ import annotations

from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def load_candles(path: str | Path) -> pd.DataFrame:
    candles = pd.read_csv(path)
    missing = [column for column in REQUIRED_COLUMNS if column not in candles.columns]
    if missing:
        raise ValueError(f"CSV is missing required columns: {', '.join(missing)}")

    candles = candles[REQUIRED_COLUMNS].copy()
    candles["timestamp"] = pd.to_datetime(candles["timestamp"], utc=True)
    candles = candles.sort_values("timestamp").drop_duplicates("timestamp")
    candles = candles.set_index("timestamp")

    numeric_columns = ["open", "high", "low", "close", "volume"]
    candles[numeric_columns] = candles[numeric_columns].apply(pd.to_numeric, errors="raise")

    if (candles[numeric_columns] <= 0).any().any():
        raise ValueError("OHLCV values must be positive")

    return candles


def resample_ohlcv(candles: pd.DataFrame, rule: str) -> pd.DataFrame:
    return (
        candles.resample(rule)
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna()
    )
