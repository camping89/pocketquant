"""Shared value objects for the domain layer."""

from pocketquant.core.domain.shared.enums import (
    Interval,  # noqa: F401 (re-export for backward compat)
)

INTERVAL_SECONDS = {
    Interval.MINUTE_1: 60,
    Interval.MINUTE_3: 180,
    Interval.MINUTE_5: 300,
    Interval.MINUTE_15: 900,
    Interval.MINUTE_30: 1800,
    Interval.MINUTE_45: 2700,
    Interval.HOUR_1: 3600,
    Interval.HOUR_2: 7200,
    Interval.HOUR_3: 10800,
    Interval.HOUR_4: 14400,
    Interval.DAY_1: 86400,
    Interval.WEEK_1: 604800,
    Interval.MONTH_1: 2592000,
}
