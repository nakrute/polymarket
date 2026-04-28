from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import pandas as pd

from btc_bot.config import BotConfig
from btc_bot.exchange import Exchange
from btc_bot.risk import RiskState, can_trade, position_size, record_trade_result
from btc_bot.strategy import Signal, add_strategy_columns, decide


LOGGER = logging.getLogger(__name__)


@dataclass
class LivePosition:
    quantity: float
    entry_price: float
    entry_fee: float
    stop_price: float
    highest_price: float
    entry_time: pd.Timestamp


class PaperTradingBot:
    def __init__(self, config: BotConfig, exchange: Exchange) -> None:
        self.config = config
        self.exchange = exchange
        self.risk_state = RiskState(starting_cash=config.risk.starting_cash)
        self.cash = config.risk.starting_cash
        self.position: LivePosition | None = None

    def on_candles(self, candles: pd.DataFrame) -> None:
        frame = add_strategy_columns(candles, self.config.strategy)
        row = frame.iloc[-1]
        close = float(row["close"])

        if self.position:
            self.position.highest_price = max(self.position.highest_price, float(row["high"]))
            trailing_stop = self.position.highest_price - (
                float(row["atr"]) * self.config.strategy.trail_atr_multiple
            )
            self.position.stop_price = max(self.position.stop_price, trailing_stop)
            signal = decide(row, in_position=True, config=self.config.strategy)
            if float(row["low"]) <= self.position.stop_price or signal.signal == Signal.EXIT_LONG:
                self._exit(close)
                return

        if self.position is None and can_trade(self.risk_state, self.config.risk):
            signal = decide(row, in_position=False, config=self.config.strategy)
            if signal.signal == Signal.ENTER_LONG:
                stop_price = close - (float(row["atr"]) * self.config.strategy.stop_atr_multiple)
                quantity = position_size(self.cash, close, stop_price, self.config.risk)
                if quantity > 0:
                    order = self.exchange.buy(self.config.symbol, quantity, close)
                    self.cash -= order.quantity * order.price + order.fee
                    self.position = LivePosition(
                        quantity=order.quantity,
                        entry_price=order.price,
                        entry_fee=order.fee,
                        stop_price=stop_price,
                        highest_price=close,
                        entry_time=row.name,
                    )
                    LOGGER.info("entered_long quantity=%s price=%s", order.quantity, order.price)

    def _exit(self, reference_price: float) -> None:
        if not self.position:
            return
        order = self.exchange.sell(self.config.symbol, self.position.quantity, reference_price)
        gross = (order.price - self.position.entry_price) * self.position.quantity
        pnl = gross - self.position.entry_fee - order.fee
        self.cash += order.quantity * order.price - order.fee
        record_trade_result(self.risk_state, pnl)
        LOGGER.info("exited_long quantity=%s price=%s pnl=%s", order.quantity, order.price, pnl)
        self.position = None


def run_loop(fetch_candles, bot: PaperTradingBot, poll_seconds: int = 30) -> None:
    while True:
        candles = fetch_candles()
        bot.on_candles(candles)
        time.sleep(poll_seconds)
