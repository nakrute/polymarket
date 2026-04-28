from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd

from btc_bot.config import StrategyConfig
from btc_bot.data import resample_ohlcv
from btc_bot.indicators import atr, ema, rsi


class Signal(str, Enum):
    HOLD = "hold"
    ENTER_LONG = "enter_long"
    EXIT_LONG = "exit_long"


@dataclass(frozen=True)
class SignalDecision:
    signal: Signal
    reason: str


def add_strategy_columns(candles: pd.DataFrame, config: StrategyConfig) -> pd.DataFrame:
    frame = candles.copy()
    frame["ema_fast"] = ema(frame["close"], config.fast_ema)
    frame["ema_slow"] = ema(frame["close"], config.slow_ema)
    frame["rsi"] = rsi(frame["close"], config.rsi_period)
    frame["atr"] = atr(frame, config.atr_period)
    frame["volume_median"] = frame["volume"].rolling(config.volume_window).median()

    hourly = resample_ohlcv(frame[["open", "high", "low", "close", "volume"]], "1h")
    hourly["regime_ema"] = ema(hourly["close"], config.regime_ema)
    hourly_regime = hourly[["close", "regime_ema"]].rename(columns={"close": "hourly_close"})
    frame = frame.join(hourly_regime.reindex(frame.index, method="ffill"))
    return frame


def decide(row: pd.Series, in_position: bool, config: StrategyConfig) -> SignalDecision:
    required = ["ema_fast", "ema_slow", "rsi", "atr", "volume_median", "hourly_close", "regime_ema"]
    if row[required].isna().any():
        return SignalDecision(Signal.HOLD, "warming_up")

    trend_ok = row["hourly_close"] > row["regime_ema"]
    momentum_ok = row["ema_fast"] > row["ema_slow"]
    rsi_ok = config.min_rsi <= row["rsi"] <= config.max_rsi
    volume_ok = row["volume"] >= row["volume_median"]

    if not in_position and trend_ok and momentum_ok and rsi_ok and volume_ok:
        return SignalDecision(Signal.ENTER_LONG, "trend_momentum_volume")

    if in_position and (not trend_ok or not momentum_ok):
        return SignalDecision(Signal.EXIT_LONG, "trend_or_momentum_broke")

    return SignalDecision(Signal.HOLD, "no_edge")
