from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyConfig:
    signal_timeframe: str = "5min"
    regime_timeframe: str = "1h"
    fast_ema: int = 20
    slow_ema: int = 50
    regime_ema: int = 200
    rsi_period: int = 14
    atr_period: int = 14
    volume_window: int = 20
    min_rsi: float = 52.0
    max_rsi: float = 72.0
    entry_mode: str = "momentum"
    pullback_tolerance_atr: float = 0.25
    max_extension_atr: float = 999.0
    atr_expansion_window: int = 50
    min_atr_expansion: float = 0.0
    min_expected_move_bps: float = 0.0
    stop_atr_multiple: float = 2.0
    trail_atr_multiple: float = 2.5
    max_holding_bars: int = 36


@dataclass(frozen=True)
class RiskConfig:
    starting_cash: float = 10_000.0
    risk_per_trade: float = 0.005
    max_daily_loss: float = 0.02
    max_consecutive_losses: int = 4
    max_notional_fraction: float = 0.95


@dataclass(frozen=True)
class ExecutionConfig:
    fee_rate: float = 0.001
    slippage_bps: float = 2.0
    min_spread_bps: float = 0.0
    max_spread_bps: float = 8.0


@dataclass(frozen=True)
class BotConfig:
    symbol: str = "BTC/USD"
    candle_minutes: int = 5
    strategy: StrategyConfig = StrategyConfig()
    risk: RiskConfig = RiskConfig()
    execution: ExecutionConfig = ExecutionConfig()
