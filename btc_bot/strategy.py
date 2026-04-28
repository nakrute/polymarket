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
    signal_frame = frame
    if config.signal_timeframe != "5min":
        signal_frame = resample_ohlcv(frame[["open", "high", "low", "close", "volume"]], config.signal_timeframe)

    signal_frame = signal_frame.copy()
    signal_frame["ema_fast"] = ema(signal_frame["close"], config.fast_ema)
    signal_frame["ema_slow"] = ema(signal_frame["close"], config.slow_ema)
    signal_frame["rsi"] = rsi(signal_frame["close"], config.rsi_period)
    signal_frame["atr"] = atr(signal_frame, config.atr_period)
    signal_frame["atr_median"] = signal_frame["atr"].rolling(config.atr_expansion_window).median()
    signal_frame["volume_median"] = signal_frame["volume"].rolling(config.volume_window).median()
    signal_frame["signal_volume"] = signal_frame["volume"]

    signal_columns = ["ema_fast", "ema_slow", "rsi", "atr", "atr_median", "signal_volume", "volume_median"]
    frame = frame.join(signal_frame[signal_columns].reindex(frame.index, method="ffill"))

    regime = resample_ohlcv(frame[["open", "high", "low", "close", "volume"]], config.regime_timeframe)
    regime["regime_ema"] = ema(regime["close"], config.regime_ema)
    regime_columns = regime[["close", "regime_ema"]].rename(columns={"close": "regime_close"})
    frame = frame.join(regime_columns.reindex(frame.index, method="ffill"))
    return frame


def decide(row: pd.Series, in_position: bool, config: StrategyConfig) -> SignalDecision:
    required = ["ema_fast", "ema_slow", "rsi", "atr", "atr_median", "signal_volume", "volume_median", "regime_close", "regime_ema"]
    if row[required].isna().any():
        return SignalDecision(Signal.HOLD, "warming_up")

    trend_ok = row["regime_close"] > row["regime_ema"]
    momentum_ok = row["ema_fast"] > row["ema_slow"]
    rsi_ok = config.min_rsi <= row["rsi"] <= config.max_rsi
    volume_ok = row["signal_volume"] >= row["volume_median"]
    pullback_ok = row["low"] <= row["ema_fast"] + (row["atr"] * config.pullback_tolerance_atr)
    extension_ok = (row["close"] - row["ema_fast"]) <= row["atr"] * config.max_extension_atr
    atr_expansion_ok = config.min_atr_expansion <= 0 or row["atr"] >= row["atr_median"] * config.min_atr_expansion
    expected_move_bps = (row["atr"] * config.trail_atr_multiple / row["close"]) * 10_000
    fee_hurdle_ok = expected_move_bps >= config.min_expected_move_bps
    entry_shape_ok = momentum_ok
    if config.entry_mode == "pullback":
        entry_shape_ok = momentum_ok and pullback_ok and row["close"] >= row["ema_fast"]
    elif config.entry_mode == "not_extended":
        entry_shape_ok = momentum_ok and extension_ok

    if not in_position and trend_ok and entry_shape_ok and rsi_ok and volume_ok and atr_expansion_ok and fee_hurdle_ok:
        return SignalDecision(Signal.ENTER_LONG, f"trend_{config.entry_mode}_filters")

    if in_position and (not trend_ok or not momentum_ok):
        return SignalDecision(Signal.EXIT_LONG, "trend_or_momentum_broke")

    return SignalDecision(Signal.HOLD, "no_edge")
