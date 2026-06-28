"""Time simulation using ContextVar for backtest support.

Uses ContextVar so simulated time is isolated to async context.
Each backtest run can have its own simulated timeline without
affecting other concurrent operations.
"""

from contextvars import ContextVar
from datetime import UTC, datetime

# ContextVar ensures time isolation per async context
_simulated_time: ContextVar[datetime | None] = ContextVar("simulated_time", default=None)


def get_current_time() -> datetime:
    """Return simulated time if set, else real UTC time.

    This function should be used throughout the codebase wherever
    current time is needed, enabling backtesting without code changes.
    """
    simulated = _simulated_time.get()
    return simulated if simulated is not None else datetime.now(UTC)


def set_simulation_time(timestamp: datetime) -> None:
    """Set simulated time for current async context.

    Args:
        timestamp: The datetime to use as "now" in backtest context.
    """
    _simulated_time.set(timestamp)


def clear_simulation_time() -> None:
    _simulated_time.set(None)


def is_simulation_active() -> bool:
    return _simulated_time.get() is not None
