"""Where the closed-market skip sits relative to the retry loop.

``fetch_with_retry``'s backoff loop reads an empty result as "try again", and a
halted CME session is a legitimately empty answer from an unofficial scraper.
These tests wire the real chain — ``_sync_by_intervals`` ->
``SyncService.sync_one`` -> ``fetch_with_retry`` ->
``RoutingDataProviderAdapter`` -> fake children — and pin two things about it:
a shut market reaches no provider at all, and an open one costs exactly one
call per attempt, all of them to the provider the suffix names.

The existing calendar-gate suite stops at ``sync_one``, which it mocks, so it
can only show the skip is upstream of the service. It cannot see either loop.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.market_data.routing_data_provider_adapter import (
    RoutingDataProviderAdapter,
)
from pocketquant.engine.market_data.app_services.sync_jobs import _sync_by_intervals
from pocketquant.engine.market_data.sync_service import SyncService

SYMBOL = "ES1!:TRADINGVIEW"


class _Shut(Continuous24x7Calendar):
    """Closed, and closed long enough ago to be past the grace window."""

    def is_open(self, instant: datetime) -> bool:
        return False

    def previous_close(self, instant: datetime) -> datetime:
        return instant - timedelta(hours=8)


def _empty_provider() -> AsyncMock:
    """A provider that is reachable and has nothing to say — the halt case."""
    provider = AsyncMock()
    provider.fetch_ohlcv = AsyncMock(return_value=[])
    return provider


def _sync_service(calendar, providers: dict[str, AsyncMock]) -> SyncService:
    bar_repo = AsyncMock()
    bar_repo.count = AsyncMock(return_value=0)
    bar_repo.get_latest = AsyncMock(return_value=None)

    calendar_factory = MagicMock()
    calendar_factory.for_symbol = AsyncMock(return_value=calendar)

    cache = AsyncMock()
    sync_status_repo = AsyncMock()
    sync_status_repo.bump_empty_fetch = AsyncMock(return_value=1)

    return SyncService(
        provider=RoutingDataProviderAdapter(
            providers=providers,  # pyright: ignore[reportArgumentType]
        ),
        cache=cache,
        bar_repository=bar_repo,
        symbol_repository=AsyncMock(),
        sync_status_repository=sync_status_repo,
        calendar_factory=calendar_factory,
    )


async def _run_job(calendar, providers: dict[str, AsyncMock]) -> MagicMock:
    tracked = MagicMock()
    tracked.symbol = SYMBOL
    tracked_repo = MagicMock()
    tracked_repo.list_all = AsyncMock(return_value=[tracked])

    calendar_factory = MagicMock()
    calendar_factory.for_symbol = AsyncMock(return_value=calendar)

    history_repo = MagicMock()
    history_repo.record_detail = AsyncMock()

    await _sync_by_intervals(
        [Interval.MINUTE_1],
        100,
        "sync_1m",
        _sync_service(calendar, providers),
        tracked_repo,
        history_repo,
        "doc-1",
        source="test",
        calendar_factory=calendar_factory,
    )
    return history_repo


def _calls(providers: dict[str, AsyncMock]) -> int:
    return sum(p.fetch_ohlcv.await_count for p in providers.values())


@pytest.mark.asyncio
async def test_a_shut_market_reaches_no_provider_through_either_loop() -> None:
    """The skip is upstream of the backoff loop.

    This is the guard that keeps a halted session from costing a burst of
    scrape calls a minute. Asserting on the children rather than on
    ``sync_one`` is the whole point: a skip that merely stopped the service
    would still let a caller elsewhere spin the loop.
    """
    providers = {"tradingview": _empty_provider(), "binance": _empty_provider()}

    await _run_job(_Shut(), providers)

    assert _calls(providers) == 0


@pytest.mark.asyncio
async def test_an_open_empty_market_costs_one_call_per_attempt_to_its_own_provider() -> None:
    """The worst case is the retry count, spent on the provider the suffix names.

    There is no provider walk to multiply it: another provider's bars for the
    same code would be a different instrument.

    The backoff delays are flattened because this pins how many calls happen,
    not how long they wait; leaving them real would add 11s of sleeping.
    """
    providers = {"tradingview": _empty_provider(), "binance": _empty_provider()}

    with patch(
        "pocketquant.engine.market_data.sync_internals.provider_fetch._BACKOFF_SECONDS",
        (0, 0, 0),
    ):
        await _run_job(Continuous24x7Calendar(), providers)

    attempts = 3
    assert providers["tradingview"].fetch_ohlcv.await_count == attempts
    providers["binance"].fetch_ohlcv.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_open_market_costs_one_call_once_the_provider_answers() -> None:
    """A provider that answers is one call, and no other provider is asked."""
    answering = AsyncMock()
    answering.fetch_ohlcv = AsyncMock(
        return_value=[
            _bar := MagicMock(
                datetime=datetime(2026, 6, 10, 12, 0, tzinfo=UTC),
                interval=Interval.MINUTE_1,
            )
        ]
    )
    fallback = _empty_provider()

    with patch(
        "pocketquant.engine.market_data.sync_internals.provider_fetch.has_aligned_bar",
        return_value=True,
    ):
        await _run_job(Continuous24x7Calendar(), {"tradingview": answering, "binance": fallback})

    assert answering.fetch_ohlcv.await_count == 1
    fallback.fetch_ohlcv.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failing_sole_provider_costs_one_call_not_three() -> None:
    """An outage must not be retried as though it were an empty market.

    The retry loop exists for a provider that answers emptily at a bar
    boundary. A provider that is refusing us is a different event, and
    retrying it three times a minute is how a rate limit becomes a ban. The
    routing adapter lets the failure propagate, which stops the retry loop at
    the first attempt.
    """
    refusing = AsyncMock()
    refusing.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("HTTP 429 rate limited"))

    history = await _run_job(Continuous24x7Calendar(), {"tradingview": refusing})

    assert refusing.fetch_ohlcv.await_count == 1
    detail = history.record_detail.await_args.kwargs
    assert detail["status"] == "error"
    assert "429" in detail["error"]
