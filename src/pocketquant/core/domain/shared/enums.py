from dataclasses import dataclass
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

        Deprecated as an annualization source: the calendar owns annualization.
        This is the 24/7 answer, kept because ``Continuous24x7Calendar`` reads
        this same table. Anything holding a calendar should ask it instead.
        """
        return _PERIODS_PER_YEAR[self.value]

    @staticmethod
    def periods_per_year_for(interval: str) -> float | None:
        """Safe lookup by raw string; returns None for an unknown interval.

        Deprecated as an annualization source, for the same reason as
        ``periods_per_year``: this is the 24/7 answer, and a symbol on a session
        calendar has a different one. Annualization callers skip scaling
        (Sharpe=0) rather than raise on a stale/queued request carrying an
        interval no longer in the enum.
        """
        return _PERIODS_PER_YEAR.get(interval)


class AssetClass(str, Enum):
    """What an instrument is, which determines how it trades and settles.

    Drives calendar selection and contract units; see
    ``pocketquant.core.domain.symbol.value_objects``.
    """

    CRYPTO_SPOT = "crypto_spot"
    CRYPTO_PERP = "crypto_perp"
    INDEX_FUTURE = "index_future"


class TradingViewPlan(str, Enum):
    """Which TradingView subscription the configured account holds.

    Nothing below ``Settings`` branches on this name. Consumers read the
    :class:`TradingViewCapabilities` record it derives, so adding a plan is one
    map entry and adding a capability is one field.
    """

    FREE = "free"
    """Delayed CME data, conservative limits. The default: works unconfigured."""

    CME_NON_PRO = "cme_non_pro"
    """The CME non-professional real-time add-on."""


@dataclass(frozen=True)
class TradingViewCapabilities:
    """What a plan permits, so no consumer has to know which plan is configured.

    ``min_poll_seconds`` is a floor rather than an interval: a caller polls at
    ``max(configured, min_poll_seconds)``. On a delayed feed, polling faster
    cannot make a quote fresher, so it buys ban risk and nothing else.
    """

    realtime: bool
    max_bars: int
    min_poll_seconds: int


# Derived from the plan by a module-level map, following the precedent
# ``_DEFAULT_CALENDAR_FOR`` set for deriving ``calendar_id`` from ``asset_class``.
# 5000 is the scraper's own documented per-request ceiling, which no plan lifts.
_CAPABILITIES_FOR: dict[TradingViewPlan, TradingViewCapabilities] = {
    TradingViewPlan.FREE: TradingViewCapabilities(
        realtime=False, max_bars=5_000, min_poll_seconds=60
    ),
    TradingViewPlan.CME_NON_PRO: TradingViewCapabilities(
        realtime=True, max_bars=5_000, min_poll_seconds=15
    ),
}


def capabilities_for(plan: TradingViewPlan) -> TradingViewCapabilities:
    """The capability record for ``plan``."""
    return _CAPABILITIES_FOR[plan]
