from __future__ import annotations

import argparse
from dataclasses import dataclass

import pandas as pd

from btc_bot.config import BotConfig
from btc_bot.data import load_candles
from btc_bot.exchange import PaperExchange
from btc_bot.risk import RiskState, can_trade, position_size, record_trade_result
from btc_bot.strategy import Signal, add_strategy_columns, decide


@dataclass
class Position:
    quantity: float
    entry_price: float
    entry_fee: float
    stop_price: float
    highest_price: float
    entry_bar: int


def run_backtest(candles: pd.DataFrame, config: BotConfig) -> dict[str, float | int]:
    frame = add_strategy_columns(candles, config.strategy)
    exchange = PaperExchange(config.execution.fee_rate, config.execution.slippage_bps)
    risk_state = RiskState(starting_cash=config.risk.starting_cash)
    cash = config.risk.starting_cash
    position: Position | None = None
    trades = 0
    wins = 0
    losses = 0
    equity_curve: list[float] = []

    for bar_index, (_, row) in enumerate(frame.iterrows()):
        close = float(row["close"])

        if position:
            position.highest_price = max(position.highest_price, float(row["high"]))
            trailing_stop = position.highest_price - (float(row["atr"]) * config.strategy.trail_atr_multiple)
            position.stop_price = max(position.stop_price, trailing_stop)
            held_too_long = bar_index - position.entry_bar >= config.strategy.max_holding_bars
            stop_hit = float(row["low"]) <= position.stop_price
            signal = decide(row, in_position=True, config=config.strategy)

            if stop_hit or held_too_long or signal.signal == Signal.EXIT_LONG:
                exit_reference = min(close, position.stop_price) if stop_hit else close
                exit_order = exchange.sell(config.symbol, position.quantity, exit_reference)
                gross = (exit_order.price - position.entry_price) * position.quantity
                pnl = gross - position.entry_fee - exit_order.fee
                cash += position.quantity * exit_order.price - exit_order.fee
                record_trade_result(risk_state, pnl)
                trades += 1
                wins += int(pnl > 0)
                losses += int(pnl <= 0)
                position = None

        if position is None and can_trade(risk_state, config.risk):
            signal = decide(row, in_position=False, config=config.strategy)
            if signal.signal == Signal.ENTER_LONG:
                stop_price = close - (float(row["atr"]) * config.strategy.stop_atr_multiple)
                quantity = position_size(cash, close, stop_price, config.risk)
                if quantity > 0:
                    entry_order = exchange.buy(config.symbol, quantity, close)
                    total_cost = quantity * entry_order.price + entry_order.fee
                    if total_cost <= cash:
                        cash -= total_cost
                        position = Position(
                            quantity=quantity,
                            entry_price=entry_order.price,
                            entry_fee=entry_order.fee,
                            stop_price=stop_price,
                            highest_price=close,
                            entry_bar=bar_index,
                        )

        position_value = position.quantity * close if position else 0.0
        equity_curve.append(cash + position_value)

    final_equity = equity_curve[-1] if equity_curve else cash
    max_equity = pd.Series(equity_curve).cummax()
    drawdown = (pd.Series(equity_curve) / max_equity - 1).min() if equity_curve else 0.0

    return {
        "starting_cash": config.risk.starting_cash,
        "final_equity": round(float(final_equity), 2),
        "return_pct": round((float(final_equity) / config.risk.starting_cash - 1) * 100, 2),
        "max_drawdown_pct": round(float(drawdown) * 100, 2),
        "trades": trades,
        "wins": wins,
        "losses": losses,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a BTC 5-minute strategy backtest.")
    parser.add_argument("--csv", required=True, help="Path to OHLCV CSV data.")
    args = parser.parse_args()

    results = run_backtest(load_candles(args.csv), BotConfig())
    for key, value in results.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
