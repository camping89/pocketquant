"""Tests for no-progress tracking + anomaly log emission.

Mocks SyncStatusRepository, BarRepository, SymbolRepository, Cache, and
IDataProvider. Patches `fetch_with_retry` so handler uses scripted
provider responses without retry overhead.

Each test asserts which sync_status_repo method was called (bump vs reset)
plus log event/level for the structured anomaly trail.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import structlog
from pocketquant.api.market_data.handlers.sync.sync_one.command import SyncSymbolCommand
from pocketquant.api.market_data.handlers.sync.sync_one.handler import SyncSymbolHandler
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval


def _bar(ts: datetime) -> Bar:
    return Bar(
        symbol="BTCUSDT",
        exchange="BINANCE",
        interval=Interval.MINUTE_15,
        datetime=ts,
        open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0,
        tick_count=1,
    )


def _aligned() -> Bar:
    return _bar(datetime(2026, 5, 5, 11, 30, tzinfo=UTC))


def _misaligned() -> Bar:
    return _bar(datetime(2026, 5, 5, 11, 31, 23, tzinfo=UTC))


def _build_handler(
    *,
    fetch_records: list[Bar],
    fetch_attempts: int = 1,
    existing_count: int = 10,
    latest_age_seconds: int = 0,
    insert_count: int = 0,
    bump_returns: int = 1,
) -> tuple[SyncSymbolHandler, dict[str, AsyncMock]]:
    """Wire a handler with mocks pre-configured for a given scenario."""
    provider = AsyncMock()
    cache = AsyncMock()
    cache.delete_pattern = AsyncMock()

    bar_repo = AsyncMock()
    bar_repo.insert_many = AsyncMock(return_value=insert_count)
    bar_repo.count = AsyncMock(return_value=existing_count)
    latest = (
        _bar(datetime.now(UTC) - timedelta(seconds=latest_age_seconds))
        if existing_count > 0
        else None
    )
    bar_repo.get_latest = AsyncMock(return_value=latest)

    symbol_repo = AsyncMock()
    symbol_repo.upsert = AsyncMock()

    sync_status_repo = AsyncMock()
    sync_status_repo.upsert = AsyncMock()
    sync_status_repo.bump_empty_fetch = AsyncMock(return_value=bump_returns)
    sync_status_repo.reset_empty_fetch = AsyncMock()

    handler = SyncSymbolHandler(
        provider=provider,
        cache=cache,
        bar_repository=bar_repo,
        symbol_repository=symbol_repo,
        sync_status_repository=sync_status_repo,
    )

    mocks = {
        "provider": provider,
        "cache": cache,
        "bar_repo": bar_repo,
        "symbol_repo": symbol_repo,
        "sync_status_repo": sync_status_repo,
    }

    # Patch fetch_with_retry so we control records + attempts directly.
    fetch_mock = AsyncMock(return_value=(fetch_records, fetch_attempts))
    patch_target = (
        "pocketquant.api.market_data.handlers.sync.sync_one.handler.fetch_with_retry"
    )
    handler._fetch_patch = patch(patch_target, fetch_mock)  # type: ignore[attr-defined]
    handler._fetch_patch.start()  # type: ignore[attr-defined]
    return handler, mocks


def _stop(handler: SyncSymbolHandler) -> None:
    handler._fetch_patch.stop()  # type: ignore[attr-defined]


def _command() -> SyncSymbolCommand:
    return SyncSymbolCommand(
        symbol="BTCUSDT", exchange="BINANCE",
        interval=Interval.MINUTE_15, n_bars=48,
    )


@pytest.mark.asyncio
async def test_empty_fetch_with_existing_data_bumps_streak() -> None:
    """Provider returned [] but DB has bars → bump only, no reset."""
    handler, mocks = _build_handler(
        fetch_records=[], existing_count=10,
        insert_count=0, bump_returns=1,
    )
    try:
        await handler.handle(_command())
    finally:
        _stop(handler)

    mocks["sync_status_repo"].bump_empty_fetch.assert_awaited_once()
    mocks["sync_status_repo"].reset_empty_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_all_misaligned_bumps_streak() -> None:
    """Provider returned only misaligned bar → all dropped → bump only."""
    handler, mocks = _build_handler(
        fetch_records=[_misaligned()], existing_count=10,
        insert_count=0, bump_returns=1,
    )
    try:
        await handler.handle(_command())
    finally:
        _stop(handler)

    mocks["sync_status_repo"].bump_empty_fetch.assert_awaited_once()
    mocks["sync_status_repo"].reset_empty_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_all_existing_filtered_bumps_streak() -> None:
    """Aligned bars but all already exist → insert_count=0 → bump."""
    handler, mocks = _build_handler(
        fetch_records=[_aligned()], existing_count=10,
        insert_count=0, bump_returns=1,
    )
    try:
        await handler.handle(_command())
    finally:
        _stop(handler)

    mocks["sync_status_repo"].bump_empty_fetch.assert_awaited_once()
    mocks["sync_status_repo"].reset_empty_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_successful_insert_resets_streak() -> None:
    """inserted_count > 0 → reset only, no bump."""
    handler, mocks = _build_handler(
        fetch_records=[_aligned()], existing_count=10,
        insert_count=2, bump_returns=0,
    )
    try:
        await handler.handle(_command())
    finally:
        _stop(handler)

    mocks["sync_status_repo"].reset_empty_fetch.assert_awaited_once()
    mocks["sync_status_repo"].bump_empty_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_streak_three_with_stale_age_emits_error() -> None:
    """streak==3 AND age > 3× cadence → ERROR stuck_threshold_crossed."""
    cadence = 900  # 15m in seconds
    handler, mocks = _build_handler(
        fetch_records=[], existing_count=10,
        latest_age_seconds=cadence * 4,  # > 3× cadence
        insert_count=0, bump_returns=3,
    )
    try:
        with structlog.testing.capture_logs() as logs:
            await handler.handle(_command())
    finally:
        _stop(handler)

    assert any(
        log.get("event") == "market_data.sync.stuck_threshold_crossed"
        and log.get("log_level") == "error"
        for log in logs
    ), f"expected stuck_threshold_crossed error log; got {logs}"


@pytest.mark.asyncio
async def test_streak_four_only_warns_no_extra_error() -> None:
    """streak==4 (already past threshold) → WARN no_progress, no extra ERROR."""
    cadence = 900
    handler, mocks = _build_handler(
        fetch_records=[], existing_count=10,
        latest_age_seconds=cadence * 5,
        insert_count=0, bump_returns=4,
    )
    try:
        with structlog.testing.capture_logs() as logs:
            await handler.handle(_command())
    finally:
        _stop(handler)

    has_error = any(
        log.get("event") == "market_data.sync.stuck_threshold_crossed" for log in logs
    )
    has_warn = any(
        log.get("event") == "market_data.sync.no_progress"
        and log.get("log_level") == "warning"
        for log in logs
    )
    assert has_warn, "expected no_progress warning"
    assert not has_error, "ERROR must only fire once at threshold crossing (streak==3)"


@pytest.mark.asyncio
async def test_first_sync_no_data_fails_no_bump_or_reset() -> None:
    """fetched=0 AND no existing bars → _fail; no bump, no reset."""
    handler, mocks = _build_handler(
        fetch_records=[], existing_count=0,
        insert_count=0, bump_returns=0,
    )
    try:
        result = await handler.handle(_command())
    finally:
        _stop(handler)

    assert result.status == "error"
    mocks["sync_status_repo"].bump_empty_fetch.assert_not_called()
    mocks["sync_status_repo"].reset_empty_fetch.assert_not_called()
