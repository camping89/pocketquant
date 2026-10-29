"""The Exness safeguards: the live-order caps."""

from dataclasses import dataclass


@dataclass
class Safeguards:
    """One object per process, read by the Exness broker on every order.

    The caps come from the environment; the entry pause is stored in Mongo and
    read on every open.
    """

    live_trading: bool
    daily_loss_cap: float | None
    max_lots: float | None
    leverage: float
    risk_per_trade: float
