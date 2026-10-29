from dataclasses import dataclass


@dataclass
class Safeguards:
    live_trading: bool
    daily_loss_cap: float | None
    max_lots: float | None
    leverage: float
    risk_per_trade: float
