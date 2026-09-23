"""TradingView history provider — implements ``IDataProviderPort``.

Policy lives here, transport lives in the client and translation in the mappers.
The two policies are the entitlement cap on how many bars may be requested, and
never returning the bar that is still forming.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pocketquant.core.common.logging import get_logger
from pocketquant.core.config import Settings
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.market_data.data_provider_port import IDataProviderPort
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
from pocketquant.core.infra.tradingview.tradingview_client_interface import ITradingViewClient
from pocketquant.core.infra.tradingview.tradingview_mappers import (
    raw_bar_to_bar,
    split_futures_symbol,
)

logger = get_logger(__name__)


class TradingViewAdapter(IDataProviderPort):
    """Historical bars for symbols TradingView serves, newest closed bar last.

    Usage:
        adapter = TradingViewAdapter(client, settings, calendar_factory)
        bars = await adapter.fetch_ohlcv("ES1!:CME_MINI", Interval.HOUR_1, 500)
    """

    def __init__(
        self,
        client: ITradingViewClient,
        settings: Settings,
        calendar_factory: TradingCalendarFactory,
    ) -> None:
        self._client = client
        self._settings = settings
        self._calendar_factory = calendar_factory

    async def fetch_ohlcv(
        self,
        symbol: str,
        interval: Interval,
        n_bars: int = 1000,
    ) -> list[Bar]:
        """Closed bars for ``symbol``, ascending by ``datetime``.

        ``symbol`` is composite ``{code}:{exchange}`` (e.g. ``ES1!:CME_MINI``).
        The request is clamped to what the configured plan entitles us to, which
        is also the scraper's own per-request ceiling.
        """
        capped = min(n_bars, self._settings.tradingview_capabilities.max_bars)
        code, exchange, fut_contract = split_futures_symbol(symbol)

        raws = await self._client.fetch_bars(
            code=code,
            exchange=exchange,
            interval=interval,
            n_bars=capped,
            fut_contract=fut_contract,
        )
        bars = [raw_bar_to_bar(raw, symbol, interval) for raw in raws]

        # The in-progress bar carries only the ticks accumulated so far, so
        # persisting it corrupts OHLCV until it closes. The cutoff comes from the
        # symbol's own calendar, so an intraday boundary is counted from the
        # session open rather than from the epoch — the same source the drop
        # filter above the sync uses, so the two can never disagree.
        calendar = await self._calendar_factory.for_symbol(symbol)
        cutoff = calendar.bar_start(datetime.now(UTC), interval)
        kept = [b for b in bars if b.datetime is not None and b.datetime < cutoff]
        # Sorted before any positional decision below: "the newest" must mean the
        # newest instant, not whatever the vendor happened to send last.
        kept.sort(key=lambda b: b.datetime or datetime.min.replace(tzinfo=UTC))

        # A delayed feed defeats the cutoff above, because the cutoff is derived
        # from OUR clock. Measured on the free plan: the newest 1m bar was 633s
        # behind and still accumulating — its close and volume both changed
        # between two fetches 75s apart. It sits comfortably before our cutoff,
        # so it is kept, persisted, and never corrected: `sync_1m` filters out
        # bars that already exist, and the cascade then builds 5m/15m/1h on top
        # of a partial bar. The vendor's frontier bar is the forming one, so on a
        # delayed feed it is dropped by position rather than by timestamp.
        #
        # Only while the market is open. Once it shuts, the frontier bar is the
        # session's genuine last bar and stays the frontier, so dropping it then
        # would leave a permanent one-bar gap every session. While open, a bar
        # dropped for being newest is persisted by a later fetch, once the feed
        # has moved past it.
        #
        # Only when the frontier survived the cutoff, too. For an interval
        # longer than the delay, the forming bar starts after our cutoff and is
        # already gone; dropping "the newest" again would discard a closed bar —
        # measured as the last closed daily and weekly bars never persisting.
        delayed_drop = 0
        frontier = max((b.datetime for b in bars if b.datetime is not None), default=None)
        if (
            kept
            and kept[-1].datetime == frontier
            and not self._settings.tradingview_capabilities.realtime
            and calendar.is_open(datetime.now(UTC))
        ):
            kept = kept[:-1]
            delayed_drop = 1

        dropped = len(bars) - len(kept)
        if dropped:
            logger.debug(
                "tradingview.in_progress_bar_filtered",
                symbol=symbol,
                interval=interval.value,
                count=dropped,
                delayed_frontier_dropped=delayed_drop,
            )


        # One-shot per symbol per interval per cron tick, which is bounded.
        logger.info(
            "tradingview.fetch_completed",
            symbol=symbol,
            interval=interval.value,
            bars_fetched=len(kept),
        )
        return kept

    async def search_symbols(self, query: str) -> list[dict]:
        """Not a TradingView capability here.

        The routing adapter delegates search to the crypto primary, so this is
        never the answer a caller gets; it exists to satisfy the port.
        """
        logger.debug("tradingview.search_not_supported", query=query)
        return []

    async def close(self) -> None:
        """Nothing to close: the scraper opens a socket per call and drops it."""
        return
