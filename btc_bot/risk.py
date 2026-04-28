from __future__ import annotations

from dataclasses import dataclass

from btc_bot.config import RiskConfig


@dataclass
class RiskState:
    starting_cash: float
    realized_pnl: float = 0.0
    daily_realized_pnl: float = 0.0
    consecutive_losses: int = 0


def can_trade(state: RiskState, config: RiskConfig) -> bool:
    daily_loss_limit = -state.starting_cash * config.max_daily_loss
    if state.daily_realized_pnl <= daily_loss_limit:
        return False
    return state.consecutive_losses < config.max_consecutive_losses


def position_size(
    cash: float,
    entry_price: float,
    stop_price: float,
    config: RiskConfig,
) -> float:
    risk_per_unit = abs(entry_price - stop_price)
    if risk_per_unit <= 0:
        return 0.0

    risk_budget = cash * config.risk_per_trade
    risk_based_units = risk_budget / risk_per_unit
    notional_cap_units = (cash * config.max_notional_fraction) / entry_price
    return max(0.0, min(risk_based_units, notional_cap_units))


def record_trade_result(state: RiskState, pnl: float) -> None:
    state.realized_pnl += pnl
    state.daily_realized_pnl += pnl
    if pnl < 0:
        state.consecutive_losses += 1
    else:
        state.consecutive_losses = 0
