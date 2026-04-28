from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from btc_bot.config import BotConfig, ExecutionConfig, RiskConfig
from btc_bot.config import StrategyConfig
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
    entry_time: pd.Timestamp
    entry_reason: str


def run_backtest(
    candles: pd.DataFrame,
    config: BotConfig,
) -> tuple[dict[str, float | int | str], pd.DataFrame]:
    frame = add_strategy_columns(candles, config.strategy)
    exchange = PaperExchange(config.execution.fee_rate, config.execution.slippage_bps)
    risk_state = RiskState(starting_cash=config.risk.starting_cash)
    cash = config.risk.starting_cash
    position: Position | None = None
    current_day = None
    trades = 0
    wins = 0
    losses = 0
    equity_curve: list[float] = []
    trade_rows: list[dict[str, float | int | str]] = []

    for bar_index, (timestamp, row) in enumerate(frame.iterrows()):
        bar_day = timestamp.date()
        if current_day != bar_day:
            current_day = bar_day
            risk_state.daily_realized_pnl = 0.0

        close = float(row["close"])
        exited_this_bar = False

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
                notional = position.entry_price * position.quantity
                exit_reason = "stop" if stop_hit else "max_holding" if held_too_long else signal.reason
                cash += position.quantity * exit_order.price - exit_order.fee
                record_trade_result(risk_state, pnl)
                trades += 1
                wins += int(pnl > 0)
                losses += int(pnl <= 0)
                trade_rows.append(
                    {
                        "entry_time": str(position.entry_time),
                        "exit_time": str(timestamp),
                        "entry_reason": position.entry_reason,
                        "exit_reason": exit_reason,
                        "quantity": position.quantity,
                        "entry_price": position.entry_price,
                        "exit_price": exit_order.price,
                        "entry_fee": position.entry_fee,
                        "exit_fee": exit_order.fee,
                        "gross_pnl": gross,
                        "net_pnl": pnl,
                        "return_pct": (pnl / notional) * 100 if notional else 0.0,
                        "bars_held": bar_index - position.entry_bar,
                    }
                )
                position = None
                exited_this_bar = True

        if position is None and not exited_this_bar and can_trade(risk_state, config.risk):
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
                            entry_time=timestamp,
                            entry_reason=signal.reason,
                        )

        position_value = position.quantity * close if position else 0.0
        equity_curve.append(cash + position_value)

    final_equity = equity_curve[-1] if equity_curve else cash
    max_equity = pd.Series(equity_curve).cummax()
    drawdown = (pd.Series(equity_curve) / max_equity - 1).min() if equity_curve else 0.0

    summary = {
        "candles": len(candles),
        "start": str(candles.index.min()) if not candles.empty else "n/a",
        "end": str(candles.index.max()) if not candles.empty else "n/a",
        "starting_cash": config.risk.starting_cash,
        "final_equity": round(float(final_equity), 2),
        "return_pct": round((float(final_equity) / config.risk.starting_cash - 1) * 100, 2),
        "max_drawdown_pct": round(float(drawdown) * 100, 2),
        "trades": trades,
        "wins": wins,
        "losses": losses,
    }
    return summary, pd.DataFrame(trade_rows)


def strategy_diagnostics(candles: pd.DataFrame, config: BotConfig) -> dict[str, int]:
    frame = add_strategy_columns(candles, config.strategy)
    required = ["ema_fast", "ema_slow", "rsi", "atr", "atr_median", "signal_volume", "volume_median", "regime_close", "regime_ema"]
    ready = frame[required].notna().all(axis=1)
    trend_ok = frame["regime_close"] > frame["regime_ema"]
    momentum_ok = frame["ema_fast"] > frame["ema_slow"]
    rsi_ok = frame["rsi"].between(config.strategy.min_rsi, config.strategy.max_rsi)
    volume_ok = frame["signal_volume"] >= frame["volume_median"]
    pullback_ok = frame["low"] <= frame["ema_fast"] + (frame["atr"] * config.strategy.pullback_tolerance_atr)
    extension_ok = (frame["close"] - frame["ema_fast"]) <= frame["atr"] * config.strategy.max_extension_atr
    atr_expansion_ok = (
        frame["atr"] >= frame["atr_median"] * config.strategy.min_atr_expansion
        if config.strategy.min_atr_expansion > 0
        else pd.Series(True, index=frame.index)
    )
    expected_move_bps = (frame["atr"] * config.strategy.trail_atr_multiple / frame["close"]) * 10_000
    fee_hurdle_ok = expected_move_bps >= config.strategy.min_expected_move_bps
    entry_shape_ok = momentum_ok
    if config.strategy.entry_mode == "pullback":
        entry_shape_ok = momentum_ok & pullback_ok & (frame["close"] >= frame["ema_fast"])
    elif config.strategy.entry_mode == "not_extended":
        entry_shape_ok = momentum_ok & extension_ok
    entry_ok = ready & trend_ok & entry_shape_ok & rsi_ok & volume_ok & atr_expansion_ok & fee_hurdle_ok

    return {
        "ready_bars": int(ready.sum()),
        "missing_regime_ema_bars": int(frame["regime_ema"].isna().sum()),
        "trend_ok_bars": int((ready & trend_ok).sum()),
        "momentum_ok_bars": int((ready & momentum_ok).sum()),
        "pullback_ok_bars": int((ready & pullback_ok).sum()),
        "extension_ok_bars": int((ready & extension_ok).sum()),
        "rsi_ok_bars": int((ready & rsi_ok).sum()),
        "volume_ok_bars": int((ready & volume_ok).sum()),
        "atr_expansion_ok_bars": int((ready & atr_expansion_ok).sum()),
        "fee_hurdle_ok_bars": int((ready & fee_hurdle_ok).sum()),
        "entry_candidate_bars": int(entry_ok.sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a BTC 5-minute strategy backtest.")
    parser.add_argument("--csv", required=True, help="Path to OHLCV CSV data.")
    parser.add_argument(
        "--regime-ema",
        type=int,
        default=200,
        help="Hourly EMA period for trend regime. Default needs about 200 hours of data.",
    )
    parser.add_argument("--signal-timeframe", default="5min", help="Signal timeframe, e.g. 5min or 15min.")
    parser.add_argument("--regime-timeframe", default="1h", help="Regime timeframe, e.g. 1h or 4h.")
    parser.add_argument("--fast-ema", type=int, default=20, help="Fast 5-minute EMA period.")
    parser.add_argument("--slow-ema", type=int, default=50, help="Slow 5-minute EMA period.")
    parser.add_argument("--min-rsi", type=float, default=52.0, help="Minimum RSI for long entries.")
    parser.add_argument("--max-rsi", type=float, default=72.0, help="Maximum RSI for long entries.")
    parser.add_argument(
        "--entry-mode",
        choices=["momentum", "pullback", "not_extended"],
        default="momentum",
        help="Entry shape filter.",
    )
    parser.add_argument("--pullback-tolerance-atr", type=float, default=0.25, help="Pullback distance above EMA in ATRs.")
    parser.add_argument("--max-extension-atr", type=float, default=999.0, help="Maximum close above fast EMA in ATRs.")
    parser.add_argument("--atr-expansion-window", type=int, default=50, help="ATR median window for expansion filter.")
    parser.add_argument("--min-atr-expansion", type=float, default=0.0, help="Require ATR >= ATR median times this value.")
    parser.add_argument("--min-expected-move-bps", type=float, default=0.0, help="Minimum ATR-derived expected move in bps.")
    parser.add_argument(
        "--fee-hurdle-multiple",
        type=float,
        default=0.0,
        help="Set min expected move to round-trip fee/slippage cost times this multiple.",
    )
    parser.add_argument(
        "--volume-window",
        type=int,
        default=20,
        help="Rolling volume median window. Use 1 to effectively disable the volume gate.",
    )
    parser.add_argument("--stop-atr", type=float, default=2.0, help="Initial stop ATR multiple.")
    parser.add_argument("--trail-atr", type=float, default=2.5, help="Trailing stop ATR multiple.")
    parser.add_argument("--max-holding-bars", type=int, default=36, help="Maximum bars to hold a trade.")
    parser.add_argument("--risk-per-trade", type=float, default=0.005, help="Fraction of cash risked per trade.")
    parser.add_argument("--max-daily-loss", type=float, default=0.02, help="Daily loss lockout as fraction of starting cash.")
    parser.add_argument("--max-losses", type=int, default=4, help="Consecutive loss lockout.")
    parser.add_argument("--fee-rate", type=float, default=0.001, help="Exchange fee rate per side, e.g. 0.001 is 0.1%.")
    parser.add_argument("--slippage-bps", type=float, default=2.0, help="Simulated slippage in basis points per side.")
    parser.add_argument("--trades-output", help="Optional path to write a trade log CSV.")
    parser.add_argument("--diagnostics", action="store_true", help="Print signal filter diagnostics.")
    args = parser.parse_args()

    round_trip_cost_bps = (args.fee_rate * 2 * 10_000) + (args.slippage_bps * 2)
    min_expected_move_bps = max(
        args.min_expected_move_bps,
        round_trip_cost_bps * args.fee_hurdle_multiple,
    )

    strategy_config = StrategyConfig(
        signal_timeframe=args.signal_timeframe,
        regime_timeframe=args.regime_timeframe,
        fast_ema=args.fast_ema,
        slow_ema=args.slow_ema,
        regime_ema=args.regime_ema,
        min_rsi=args.min_rsi,
        max_rsi=args.max_rsi,
        entry_mode=args.entry_mode,
        pullback_tolerance_atr=args.pullback_tolerance_atr,
        max_extension_atr=args.max_extension_atr,
        atr_expansion_window=args.atr_expansion_window,
        min_atr_expansion=args.min_atr_expansion,
        min_expected_move_bps=min_expected_move_bps,
        volume_window=args.volume_window,
        stop_atr_multiple=args.stop_atr,
        trail_atr_multiple=args.trail_atr,
        max_holding_bars=args.max_holding_bars,
    )
    risk_config = RiskConfig(
        risk_per_trade=args.risk_per_trade,
        max_daily_loss=args.max_daily_loss,
        max_consecutive_losses=args.max_losses,
    )
    execution_config = ExecutionConfig(fee_rate=args.fee_rate, slippage_bps=args.slippage_bps)
    config = BotConfig(strategy=strategy_config, risk=risk_config, execution=execution_config)
    candles = load_candles(args.csv)
    results, trades = run_backtest(candles, config)
    for key, value in results.items():
        print(f"{key}: {value}")

    if not trades.empty:
        print(f"avg_trade_return_pct: {trades['return_pct'].mean():.4f}")
        print(f"avg_bars_held: {trades['bars_held'].mean():.2f}")
        print("exit_reasons:")
        for reason, count in trades["exit_reason"].value_counts().items():
            print(f"  {reason}: {count}")

    if args.trades_output:
        trades_path = Path(args.trades_output)
        trades_path.parent.mkdir(parents=True, exist_ok=True)
        trades.to_csv(trades_path, index=False)
        print(f"saved {len(trades)} trades to {trades_path}")

    if args.diagnostics:
        print("\ndiagnostics:")
        for key, value in strategy_diagnostics(candles, config).items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
