from contextvars import ContextVar
from datetime import UTC, datetime

# ContextVar ensures time isolation per async context
_simulated_time: ContextVar[datetime | None] = ContextVar("simulated_time", default=None)


def get_current_time() -> datetime:
    simulated = _simulated_time.get()
    return simulated if simulated is not None else datetime.now(UTC)


def set_simulation_time(timestamp: datetime) -> None:
    _simulated_time.set(timestamp)


def clear_simulation_time() -> None:
    _simulated_time.set(None)
