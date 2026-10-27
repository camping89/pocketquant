from dataclasses import dataclass


@dataclass(frozen=True)
class PositionCalculation:
    size: float  # base units
    notional: float  # size * entry_price
    risk_amount: float  # account_balance * risk_per_trade (capital at risk)
    est_entry_commission: float  # estimated entry fee (0.0 without a CommissionModel)
