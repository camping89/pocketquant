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

    # The 24/7 answer, kept because Continuous24x7Calendar reads this table. Anything
    # holding a calendar asks the calendar instead.
    @property
    def periods_per_year(self) -> float:
        return _PERIODS_PER_YEAR[self.value]

    # None, not an error, for a stale or queued request carrying a removed interval;
    # callers then skip annualization (Sharpe = 0).
    @staticmethod
    def periods_per_year_for(interval: str) -> float | None:
        return _PERIODS_PER_YEAR.get(interval)


class AssetClass(str, Enum):
    CRYPTO_SPOT = "crypto_spot"
    CRYPTO_PERP = "crypto_perp"
    CFD = "cfd"
