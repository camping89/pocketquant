"""Tests for no-progress tracking.

Mocks SyncStatusRepository, BarRepository, SymbolRepository, Cache, and
IDataProviderPort. Patches `fetch_with_retry` so service uses scripted
provider responses without retry overhead.

Each test asserts which sync_status_repo method was called (bump vs reset).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.engine.market_data.sync_service import SyncService, SyncSymbolCommand


def _bar(ts: datetime) -> Bar:
    return Bar(
        symbol="BINANCE:BTCUSDT",
        interval=Interval.MINUTE_15,
        datetime=ts,
        open=1.0,
        high=1.0,
        low=1.0,
        close=1.0,
        volume=1.0,
        tick_count=1,
    )


def _aligned() -> Bar:
    return _bar(datetime(2026, 5, 5, 11, 30, tzinfo=UTC))


def _misaligned() -> Bar:
    return _bar(datetime(2026, 5, 5, 11, 31, 23, tzinfo=UTC))


def _build_service(
    *,
    fetch_records: list[Bar],
    fetch_attempts: int = 1,
    existing_count: int = 10,
    latest_age_seconds: int = 0,
    insert_count: int = 0,
    bump_returns: int = 1,
) -> tuple[SyncService, dict[str, AsyncMock]]:
    """Wire a SyncService with mocks pre-configured for a given scenario."""
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

    svc = SyncService(
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
    patch_target = "pocketquant.engine.market_data.sync_service.fetch_with_retry"
    svc._fetch_patch = patch(patch_target, fetch_mock)  # type: ignore[attr-defined]
    svc._fetch_patch.start()  # type: ignore[attr-defined]
    return svc, mocks


def _stop(svc: SyncService) -> None:
    svc._fetch_patch.stop()  # type: ignore[attr-defined]


def _command() -> SyncSymbolCommand:
    return SyncSymbolCommand(
        symbol="BINANCE:BTCUSDT",
        interval=Interval.MINUTE_15,
        n_bars=48,
        source="test",
    )


@pytest.mark.asyncio
async def test_empty_fetch_with_existing_data_bumps_streak() -> None:
    """Provider returned [] but DB has bars → bump only, no reset."""
    svc, mocks = _build_service(
        fetch_records=[],
        existing_count=10,
        insert_count=0,
        bump_returns=1,
    )
    try:
        await svc.sync_one(_command())
    finally:
        _stop(svc)

    mocks["sync_status_repo"].bump_empty_fetch.assert_awaited_once()
    mocks["sync_status_repo"].reset_empty_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_all_misaligned_bumps_streak() -> None:
    """Provider returned only misaligned bar → all dropped → bump only."""
    svc, mocks = _build_service(
        fetch_records=[_misaligned()],
        existing_count=10,
        insert_count=0,
        bump_returns=1,
    )
    try:
        await svc.sync_one(_command())
    finally:
        _stop(svc)

    mocks["sync_status_repo"].bump_empty_fetch.assert_awaited_once()
    mocks["sync_status_repo"].reset_empty_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_all_existing_filtered_bumps_streak() -> None:
    """Aligned bars but all already exist → insert_count=0 → bump."""
    svc, mocks = _build_service(
        fetch_records=[_aligned()],
        existing_count=10,
        insert_count=0,
        bump_returns=1,
    )
    try:
        await svc.sync_one(_command())
    finally:
        _stop(svc)

    mocks["sync_status_repo"].bump_empty_fetch.assert_awaited_once()
    mocks["sync_status_repo"].reset_empty_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_successful_insert_resets_streak() -> None:
    """inserted_count > 0 → reset only, no bump."""
    svc, mocks = _build_service(
        fetch_records=[_aligned()],
        existing_count=10,
        insert_count=2,
        bump_returns=0,
    )
    try:
        await svc.sync_one(_command())
    finally:
        _stop(svc)

    mocks["sync_status_repo"].reset_empty_fetch.assert_awaited_once()
    mocks["sync_status_repo"].bump_empty_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_first_sync_no_data_fails_no_bump_or_reset() -> None:
    """fetched=0 AND no existing bars → _fail; no bump, no reset."""
    svc, mocks = _build_service(
        fetch_records=[],
        existing_count=0,
        insert_count=0,
        bump_returns=0,
    )
    try:
        result = await svc.sync_one(_command())
    finally:
        _stop(svc)

    assert result.status == "error"
    mocks["sync_status_repo"].bump_empty_fetch.assert_not_called()
    mocks["sync_status_repo"].reset_empty_fetch.assert_not_called()
