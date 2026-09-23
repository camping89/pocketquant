"""TradingView realtime quotes by polling — implements ``IRealtimeQuoteProviderPort``.

TradingView offers this scraper no push stream, so each subscribed symbol gets
one task that polls the newest 1m bar while its session is open and emits a
quote when the price moves. The emitted dict is the Binance ``@aggTrade`` shape
(``binance_mappers.aggtrade_to_quote_dict``), so ``QuoteAppService`` and the bar
builder need no change.

Two consequences of polling that consumers should know:

- ``volume`` is a per-emission DELTA, because ``add_tick`` accumulates it. The
  poller remembers the bar total it last emitted and sends the growth since;
  a poll that emits nothing leaves that baseline alone, so its volume is
  carried into the next emission rather than lost.
- ``tick_count`` downstream is one per emission, so it measures poll cadence
  and price changes, not market activity.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pocketquant.core.common.logging import get_logger
from pocketquant.core.config import Settings
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
from pocketquant.core.infra.tradingview.tradingview_client_interface import ITradingViewClient
from pocketquant.core.infra.tradingview.tradingview_mappers import split_futures_symbol

logger = get_logger(__name__)

# The newest bar plus one: enough to pick the latest even if the vendor
# appends a bar mid-request, while keeping each poll as light as possible.
_POLL_BARS = 2
# Anonymous scrapes drop about one connection in nine, and the next poll heals
# it. Only a run of failures is worth a WARNING.
_WARN_AFTER_FAILURES = 3

QuoteCallback = Callable[[dict[str, Any]], Any]


class TradingViewQuoteAdapter:
    """Poll the newest 1m bar per symbol while its market is open.

    Usage:
        adapter = TradingViewQuoteAdapter(client, settings, calendar_factory)
        await adapter.subscribe("ES1!:CME_MINI", on_quote)
        await adapter.run_forever()   # blocks until cancelled
    """

    def __init__(
        self,
        client: ITradingViewClient,
        settings: Settings,
        calendar_factory: TradingCalendarFactory,
    ) -> None:
        self._client = client
        self._calendar_factory = calendar_factory
        capabilities = settings.tradingview_capabilities
        # Faster than the plan's floor cannot make a delayed quote fresher; it
        # only adds ban risk.
        self._poll_seconds = max(
            settings.tradingview_poll_seconds or capabilities.min_poll_seconds,
            capabilities.min_poll_seconds,
        )
        self._subscriptions: dict[str, QuoteCallback] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        # symbol -> (bar datetime, bar volume, close) as last emitted.
        self._last_emitted: dict[str, tuple[datetime, float, float]] = {}
        self._failures: dict[str, int] = {}
        self._never_set = asyncio.Event()
        self.last_tick_at: datetime | None = None

    @property
    def poll_seconds(self) -> int:
        return self._poll_seconds

    async def connect(self) -> None:
        for symbol in self._subscriptions:
            self._start(symbol)

    async def disconnect(self) -> None:
        for symbol in list(self._tasks):
            await self._stop(symbol)
        logger.info("tradingview_quote.disconnected")

    async def subscribe(self, symbol: str, callback: QuoteCallback) -> str:
        """Register ``symbol`` (composite ``{code}:{exchange}``) and start polling it."""
        composite = symbol.upper()
        # Validates the composite now rather than on the first poll.
        split_futures_symbol(composite)
        self._subscriptions[composite] = callback
        self._start(composite)
        logger.info("tradingview_quote.subscribed", symbol=composite, poll_s=self._poll_seconds)
        return composite

    async def unsubscribe(self, symbol: str) -> None:
        composite = symbol.upper()
        if self._subscriptions.pop(composite, None) is None:
            return
        await self._stop(composite)
        self._last_emitted.pop(composite, None)
        self._failures.pop(composite, None)
        logger.info("tradingview_quote.unsubscribed", symbol=composite)

    async def run_forever(self) -> None:
        # The poll tasks do the work; this only parks the caller the way the
        # WebSocket adapter's receive loop does. CancelledError propagates.
        await self._never_set.wait()

    def is_connected(self) -> bool:
        """True while at least one symbol is polling without a failure streak.

        Not ``client.is_authenticated()``: that reports an account login, and an
        anonymous session polls perfectly well.
        """
        return any(self._failures.get(s, 0) < _WARN_AFTER_FAILURES for s in self._tasks)

    @property
    def subscription_count(self) -> int:
        return len(self._subscriptions)

    @property
    def subscriptions(self) -> dict[str, QuoteCallback]:
        return self._subscriptions

    # --- polling -------------------------------------------------------------

    def _start(self, symbol: str) -> None:
        task = self._tasks.get(symbol)
        if task is not None and not task.done():
            return
        self._tasks[symbol] = asyncio.create_task(
            self._poll_loop(symbol), name=f"tradingview_quote:{symbol}"
        )

    async def _stop(self, symbol: str) -> None:
        task = self._tasks.pop(symbol, None)
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _poll_loop(self, symbol: str) -> None:
        while True:
            try:
                await self._poll_once(symbol)
            except Exception as exc:
                # A calendar lookup or subscriber failure must not end the feed;
                # fetch failures are counted separately in ``_poll_once``.
                logger.error("tradingview_quote.poll_error", symbol=symbol, error=str(exc))
            await asyncio.sleep(self._poll_seconds)

    async def _poll_once(self, symbol: str) -> None:
        """One poll: quiet while closed, one emission when the price moved."""
        calendar = await self._calendar_factory.for_symbol(symbol)
        if not calendar.is_open(datetime.now(UTC)):
            return

        code, exchange, fut_contract = split_futures_symbol(symbol)
        try:
            raws = await self._client.fetch_bars(
                code=code,
                exchange=exchange,
                interval=Interval.MINUTE_1,
                n_bars=_POLL_BARS,
                fut_contract=fut_contract,
            )
        except Exception as exc:
            self._record_failure(symbol, exc)
            return
        self._record_success(symbol)

        if not raws:
            logger.debug("tradingview_quote.empty", symbol=symbol)
            return
        newest = max(raws, key=lambda r: r.epoch_seconds)
        bar_dt = datetime.fromtimestamp(newest.epoch_seconds, tz=UTC)

        previous = self._last_emitted.get(symbol)
        if previous is not None and previous[2] == newest.close:
            logger.debug("tradingview_quote.unchanged", symbol=symbol, close=newest.close)
            return

        volume = newest.volume
        if previous is not None and previous[0] == bar_dt:
            volume = newest.volume - previous[1]
            if volume < 0:
                # An upstream revision can lower a bar's running total.
                logger.debug(
                    "tradingview_quote.volume_revised_down",
                    symbol=symbol,
                    previous=previous[1],
                    current=newest.volume,
                )
                volume = 0.0

        self._last_emitted[symbol] = (bar_dt, newest.volume, newest.close)
        quote = {
            "symbol": symbol,
            "timestamp": bar_dt,
            "last_price": newest.close,
            "volume": volume,
            "bid": None,
            "ask": None,
            "change": None,
            "change_percent": None,
            "open_price": None,
            "high_price": None,
            "low_price": None,
            "prev_close": None,
        }
        self.last_tick_at = datetime.now(UTC)
        logger.debug("tradingview_quote.emitted", symbol=symbol, price=newest.close, volume=volume)

        callback = self._subscriptions.get(symbol)
        if callback is None:
            return
        result = callback(quote)
        if inspect.isawaitable(result):
            await result

    def _record_failure(self, symbol: str, exc: Exception) -> None:
        count = self._failures.get(symbol, 0) + 1
        self._failures[symbol] = count
        if count == _WARN_AFTER_FAILURES:
            logger.warning(
                "tradingview_quote.poll_failing", symbol=symbol, failures=count, error=str(exc)
            )
        else:
            logger.debug("tradingview_quote.poll_failed", symbol=symbol, error=str(exc))

    def _record_success(self, symbol: str) -> None:
        if self._failures.pop(symbol, 0) >= _WARN_AFTER_FAILURES:
            logger.info("tradingview_quote.poll_recovered", symbol=symbol)
