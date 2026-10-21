"""The Exness safeguards: the live-order caps and the entry pause."""

from dataclasses import dataclass

from pocketquant.core.common.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Safeguards:
    """One object per process, read by the Exness broker on every order.

    The caps come from the environment. ``entries_paused`` is loaded from the
    store at startup and written on every pause and resume, so it survives a
    restart. The pause blocks opens only; a close is never gated.
    """

    live_trading: bool
    daily_loss_cap: float | None
    max_lots: float | None
    leverage: float
    risk_per_trade: float
    entries_paused: bool = False

    def set_entries_paused(self, paused: bool) -> None:
        self.entries_paused = paused
        event = (
            "exness.safeguards.entries_paused" if paused else "exness.safeguards.entries_resumed"
        )
        logger.warning(event)
