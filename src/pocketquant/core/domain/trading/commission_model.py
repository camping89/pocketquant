from typing import Protocol


class CommissionModel(Protocol):
    def compute(self, price: float, quantity: float) -> float: ...


class PercentageCommissionModel:
    def __init__(self, bps: float) -> None:
        self._bps = bps

    def compute(self, price: float, quantity: float) -> float:
        return abs(price * quantity) * self._bps / 10_000
