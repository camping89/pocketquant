from dataclasses import dataclass


@dataclass(frozen=True)
class PositionCalculation:
    size: float  # base units
    notional: float  # size * entry_price
    risk_amount: float  # account_balance * risk_per_trade (vốn đặt rủi ro)
    est_entry_commission: float  # ước phí entry (0.0 nếu không có CommissionModel)
