from datetime import UTC, datetime

from pocketquant.core.common.time.simulation import (
    clear_simulation_time,
    get_current_time,
    set_simulation_time,
)

_UTC_FMT = "%Y-%m-%dT%H:%M:%SZ"


def utc_now() -> datetime:
    """Return the current UTC datetime (timezone-aware)."""
    return datetime.now(UTC)


def coerce_utc(value: datetime | None) -> datetime | None:
    """Ensure a datetime is UTC. Naive → UTC attached; aware → converted."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def to_utc_iso(dt: datetime | None) -> str | None:
    """Format a datetime as UTC ISO-8601 string (YYYY-MM-DDTHH:MM:SSZ), or None."""
    if dt is None:
        return None
    return dt.astimezone(UTC).strftime(_UTC_FMT)


__all__ = [
    "get_current_time",
    "set_simulation_time",
    "clear_simulation_time",
    "utc_now",
    "coerce_utc",
    "to_utc_iso",
]
