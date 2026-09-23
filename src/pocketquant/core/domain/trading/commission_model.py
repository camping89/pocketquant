from typing import Protocol


class CommissionModel(Protocol):
    def compute(self, price: float, quantity: float) -> float: ...


class PercentageCommissionModel:
    def __init__(self, bps: float) -> None:
        self._bps = bps

    def compute(self, price: float, quantity: float) -> float:
        return abs(price * quantity) * self._bps / 10_000


class PerContractCommissionModel:
    """Flat fee per contract, the CME convention. `quantity` is contracts."""

    def __init__(self, usd_per_contract: float) -> None:
        self._usd_per_contract = usd_per_contract

    def compute(self, price: float, quantity: float) -> float:
        return abs(quantity) * self._usd_per_contract


def commission_model_for(usd_per_contract: float | None, bps: float) -> CommissionModel:
    """Per-contract when a fee is configured, else percentage of notional."""
    if usd_per_contract is not None:
        return PerContractCommissionModel(usd_per_contract)
    return PercentageCommissionModel(bps=bps)
