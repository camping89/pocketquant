from enum import Enum

# Crypto trades every calendar day, so a year is 365 days for annualization.
_DAYS_PER_YEAR = 365
_PERIODS_PER_YEAR: dict[str, float] = {
    "1m": _DAYS_PER_YEAR * 24 * 60,  # 525600
    "5m": _DAYS_PER_YEAR * 24 * 12,  # 105120
    "15m": _DAYS_PER_YEAR * 24 * 4,  # 35040
    "1h": _DAYS_PER_YEAR * 24,  # 8760
    "4h": _DAYS_PER_YEAR * 6,  # 2190
    "1d": _DAYS_PER_YEAR,  # 365
    "1w": _DAYS_PER_YEAR / 7,  # 52.142857...
}


class Interval(str, Enum):
    MINUTE_1 = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    DAY_1 = "1d"
    WEEK_1 = "1w"

    @property
    def periods_per_year(self) -> float:
        """Number of bars of this interval in one calendar year (crypto, 365d).

        Used to annualize per-bar return statistics (Sharpe/Sortino).
        """
        return _PERIODS_PER_YEAR[self.value]

    @staticmethod
    def periods_per_year_for(interval: str) -> float | None:
        """Safe lookup by raw string; returns None for an unknown interval.

        Annualization callers skip scaling (Sharpe=0) rather than raise on a
        stale/queued request carrying an interval no longer in the enum.
        """
        return _PERIODS_PER_YEAR.get(interval)
