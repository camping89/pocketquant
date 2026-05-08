"""Tests for fetch_with_retry — bounded retry on empty / all-misaligned response.

Mocks IDataProvider with scripted return-sequences. Patches asyncio.sleep
for fast execution. Uses structlog.testing.capture_logs for log assertion.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
import structlog
from pocketquant.api.market_data.handlers.sync.sync_one import provider_fetch
from pocketquant.api.market_data.handlers.sync.sync_one.provider_fetch import (
    fetch_with_retry,
)
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval


def _aligned_bar(ts: str = "2026-05-05T11:30:00+00:00") -> Bar:
    return Bar(
        symbol="BTCUSDT",
        exchange="BINANCE",
        interval=Interval.MINUTE_15,
        datetime=datetime.fromisoformat(ts),
        open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0,
        tick_count=1,
    )


def _misaligned_bar(ts: str = "2026-05-05T11:31:23+00:00") -> Bar:
    return Bar(
        symbol="BTCUSDT",
        exchange="BINANCE",
        interval=Interval.MINUTE_15,
        datetime=datetime.fromisoformat(ts),
        open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0,
        tick_count=1,
    )


@pytest.fixture
def fast_sleep() -> Iterator[AsyncMock]:
    """Patch asyncio.sleep with an awaitable mock that records call args."""
    sleep_mock = AsyncMock()
    with patch.object(provider_fetch.asyncio, "sleep", sleep_mock):
        yield sleep_mock


@pytest.fixture
def fake_provider() -> AsyncMock:
    """Mock IDataProvider.fetch_ohlcv with scripted side_effects per test."""
    provider = AsyncMock()
    provider.fetch_ohlcv = AsyncMock()
    return provider


@pytest.mark.asyncio
async def test_attempt_one_succeeds_no_sleep(
    fast_sleep: AsyncMock, fake_provider: AsyncMock,
) -> None:
    """Provider returns aligned bars on first try → attempts=1, no sleeps."""
    fake_provider.fetch_ohlcv.return_value = [_aligned_bar()]

    records, attempts = await fetch_with_retry(
        fake_provider, "BTCUSDT", "BINANCE", Interval.MINUTE_15, 48,
    )

    assert attempts == 1
    assert len(records) == 1
    fast_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_empty_then_aligned_recovers(
    fast_sleep: AsyncMock, fake_provider: AsyncMock,
) -> None:
    """Provider returns [] then aligned → attempts=2, slept ~3s, fetch_recovered logged."""
    fake_provider.fetch_ohlcv.side_effect = [
        [],
        [_aligned_bar()],
    ]

    with structlog.testing.capture_logs() as logs:
        records, attempts = await fetch_with_retry(
            fake_provider, "BTCUSDT", "BINANCE", Interval.MINUTE_15, 48,
        )

    assert attempts == 2
    assert len(records) == 1
    fast_sleep.assert_called_once_with(3)
    assert any(log.get("event") == "market_data.sync.fetch_recovered" for log in logs)


@pytest.mark.asyncio
async def test_all_misaligned_then_aligned(
    fast_sleep: AsyncMock, fake_provider: AsyncMock,
) -> None:
    """Provider returns all-misaligned then aligned → attempts=2, slept ~3s."""
    fake_provider.fetch_ohlcv.side_effect = [
        [_misaligned_bar()],
        [_aligned_bar()],
    ]

    records, attempts = await fetch_with_retry(
        fake_provider, "BTCUSDT", "BINANCE", Interval.MINUTE_15, 48,
    )

    assert attempts == 2
    assert len(records) == 1
    fast_sleep.assert_called_once_with(3)


@pytest.mark.asyncio
async def test_three_empty_exhausts_retries(
    fast_sleep: AsyncMock, fake_provider: AsyncMock,
) -> None:
    """Provider returns [] × 3 → attempts=3, slept (3, 8), returns []."""
    fake_provider.fetch_ohlcv.side_effect = [[], [], []]

    records, attempts = await fetch_with_retry(
        fake_provider, "BTCUSDT", "BINANCE", Interval.MINUTE_15, 48,
    )

    assert attempts == 3
    assert records == []
    assert fast_sleep.call_count == 2
    assert [c.args[0] for c in fast_sleep.call_args_list] == [3, 8]


@pytest.mark.asyncio
async def test_three_misaligned_exhausts_retries(
    fast_sleep: AsyncMock, fake_provider: AsyncMock,
) -> None:
    """Provider returns all-misaligned × 3 → attempts=3, returns last misaligned batch."""
    misaligned = [_misaligned_bar()]
    fake_provider.fetch_ohlcv.side_effect = [misaligned, misaligned, misaligned]

    records, attempts = await fetch_with_retry(
        fake_provider, "BTCUSDT", "BINANCE", Interval.MINUTE_15, 48,
    )

    assert attempts == 3
    assert len(records) == 1  # the misaligned record returned unchanged
    assert fast_sleep.call_count == 2


@pytest.mark.asyncio
async def test_time_budget_exhausted_breaks_early(
    fast_sleep: AsyncMock, fake_provider: AsyncMock
) -> None:
    """Time budget exhausted before retry sleep → breaks early, fewer attempts."""
    fake_provider.fetch_ohlcv.return_value = []

    # Budget is 15s; we simulate time advancing past it after the first fetch.
    # monotonic() called: deadline init, then 2 budget checks per retry iteration.
    monotonic_values = iter([
        0.0,    # deadline init: deadline = 15.0
        14.0,   # budget check before sleep(3): 14 + 3 = 17 > 15 → break
    ])

    with patch.object(provider_fetch.time, "monotonic", side_effect=lambda: next(monotonic_values)):
        records, attempts = await fetch_with_retry(
            fake_provider, "BTCUSDT", "BINANCE", Interval.MINUTE_15, 48,
        )

    # First attempt fetched (no sleep, delay=0). Second attempt's sleep skipped
    # because budget would overflow → only 1 actual attempt completed.
    assert attempts == 1
    assert records == []
    fast_sleep.assert_not_called()
