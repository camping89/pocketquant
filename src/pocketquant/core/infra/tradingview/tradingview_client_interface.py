"""The seam between the TradingView scraper and everything that uses it.

The scraper is unofficial and its login has broken before, so replacing it must
be one new class rather than an edit across the adapter. Nothing library-shaped
crosses this interface: the currency is :class:`RawBar`, an instant plus OHLCV.

The instant is an epoch, deliberately. ``tvDatafeed`` builds each DataFrame
index entry with ``datetime.fromtimestamp(...)`` and no timezone, so the value
it hands back means nothing without knowing the host zone it was built in. The
client recovers the true epoch at the boundary and nothing downstream has to
know the trap existed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pocketquant.core.domain.shared.enums import Interval


@dataclass(frozen=True)
class RawBar:
    """One bar as the provider reported it: a UTC epoch plus OHLCV."""

    epoch_seconds: float
    open: float
    high: float
    low: float
    close: float
    volume: float


class ITradingViewClient(Protocol):
    """What the adapter needs from a TradingView data source."""

    async def fetch_bars(
        self,
        code: str,
        exchange: str,
        interval: Interval,
        n_bars: int,
        fut_contract: int | None,
    ) -> list[RawBar]:
        """Up to ``n_bars`` most recent bars for ``code`` on ``exchange``."""
        ...

    def is_authenticated(self) -> bool:
        """True when the underlying session holds a real account token."""
        ...
