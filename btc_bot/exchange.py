from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class OrderResult:
    symbol: str
    side: str
    quantity: float
    price: float
    fee: float


class Exchange(Protocol):
    def buy(self, symbol: str, quantity: float, reference_price: float) -> OrderResult:
        ...

    def sell(self, symbol: str, quantity: float, reference_price: float) -> OrderResult:
        ...


class PaperExchange:
    def __init__(self, fee_rate: float, slippage_bps: float) -> None:
        self.fee_rate = fee_rate
        self.slippage = slippage_bps / 10_000

    def buy(self, symbol: str, quantity: float, reference_price: float) -> OrderResult:
        price = reference_price * (1 + self.slippage)
        fee = price * quantity * self.fee_rate
        return OrderResult(symbol=symbol, side="buy", quantity=quantity, price=price, fee=fee)

    def sell(self, symbol: str, quantity: float, reference_price: float) -> OrderResult:
        price = reference_price * (1 - self.slippage)
        fee = price * quantity * self.fee_rate
        return OrderResult(symbol=symbol, side="sell", quantity=quantity, price=price, fee=fee)
