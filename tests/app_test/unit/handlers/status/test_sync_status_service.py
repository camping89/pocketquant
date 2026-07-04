"""Tests for SyncStatusQueryService — bar-derived freshness composition (list + single-symbol)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.sync_status.entities import SyncStatus
from pocketquant.engine.market_data.sync_status_service import (
    GetSymbolSyncStatusQuery,
    GetSyncStatusQuery,
    SyncStatusQueryService,
)

SYMBOL = "BINANCE:BTCUSDT"
NOW = datetime.now(UTC)


def _status(interval: str, last_bar_age_seconds: int, bar_count: int = 1000) -> SyncStatus:
    """Build SyncStatus with last_bar_at set to NOW - age."""
    return SyncStatus(
        symbol=SYMBOL,
        interval=interval,
        status="completed",
        bar_count=bar_count,
        last_sync_at=NOW - timedelta(seconds=last_bar_age_seconds),
        last_bar_at=NOW - timedelta(seconds=last_bar_age_seconds),
    )


def _bar(dt: datetime, interval: Interval) -> Bar:
    return Bar(
        symbol=SYMBOL,
        interval=interval,
        datetime=dt,
        open=1.0,
        high=1.0,
        low=1.0,
        close=1.0,
        volume=1.0,
        tick_count=1,
    )


@pytest.fixture
def sync_status_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def bar_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def handler(sync_status_repo, bar_repo) -> SyncStatusQueryService:
    return SyncStatusQueryService(sync_status_repo, bar_repo)


# get_sync_status — list of all tracked symbols/intervals


@pytest.mark.asyncio
async def test_cascade_fresh_bars_show_not_stuck(handler, sync_status_repo, bar_repo) -> None:
    """sync_status.last_bar_at stale (1h old, 5m cadence → would be stuck);
    bar_repo.get_latest fresh (1m old) → is_stuck=False."""
    sync_status_repo.find_all.return_value = [
        _status("5m", last_bar_age_seconds=3600, bar_count=100),
    ]
    bar_repo.get_latest.return_value = _bar(NOW - timedelta(seconds=60), Interval.MINUTE_5)
    bar_repo.count.return_value = 150

    result = await handler.get_sync_status(GetSyncStatusQuery())

    assert len(result) == 1
    assert result[0].is_stuck is False
    assert result[0].bar_count == 150  # ← from bars, not sync_status (100)


@pytest.mark.asyncio
async def test_all_stuck_when_bars_old(handler, sync_status_repo, bar_repo) -> None:
    """Bar age > 3× cadence → is_stuck=True."""
    sync_status_repo.find_all.return_value = [_status("5m", last_bar_age_seconds=60)]
    bar_repo.get_latest.return_value = _bar(NOW - timedelta(seconds=2000), Interval.MINUTE_5)
    bar_repo.count.return_value = 10

    result = await handler.get_sync_status(GetSyncStatusQuery())

    # 5m cadence = 300s; 3× = 900s; bar age 2000s > 900s → stuck
    assert result[0].is_stuck is True


@pytest.mark.asyncio
async def test_no_bars_yet_returns_not_stuck(handler, sync_status_repo, bar_repo) -> None:
    """get_latest returns None → is_stuck=False (matches existing semantic)."""
    sync_status_repo.find_all.return_value = [_status("5m", last_bar_age_seconds=60)]
    bar_repo.get_latest.return_value = None
    bar_repo.count.return_value = 0

    result = await handler.get_sync_status(GetSyncStatusQuery())

    assert result[0].is_stuck is False
    assert result[0].bar_count == 0
    assert result[0].last_bar_at is None


@pytest.mark.asyncio
async def test_count_overrides_status_count(handler, sync_status_repo, bar_repo) -> None:
    """sync_status.bar_count is ignored; bars actual count wins."""
    sync_status_repo.find_all.return_value = [_status("1h", last_bar_age_seconds=60, bar_count=999)]
    bar_repo.get_latest.return_value = _bar(NOW - timedelta(seconds=60), Interval.HOUR_1)
    bar_repo.count.return_value = 5907

    result = await handler.get_sync_status(GetSyncStatusQuery())

    assert result[0].bar_count == 5907


@pytest.mark.asyncio
async def test_per_row_exception_isolated_with_fallback(
    handler,
    sync_status_repo,
    bar_repo,
) -> None:
    """1 row's enrichment raises → that row falls back to sync_status fields; others succeed."""
    sync_status_repo.find_all.return_value = [
        _status("5m", last_bar_age_seconds=60, bar_count=10),
        _status("15m", last_bar_age_seconds=60, bar_count=20),
    ]

    fresh_bar = _bar(NOW - timedelta(seconds=60), Interval.MINUTE_15)

    async def get_latest_side_effect(symbol, interval):
        if interval == Interval.MINUTE_5:
            raise RuntimeError("boom")
        return fresh_bar

    async def count_side_effect(symbol, interval):
        if interval == Interval.MINUTE_5:
            raise RuntimeError("boom")
        return 999

    bar_repo.get_latest.side_effect = get_latest_side_effect
    bar_repo.count.side_effect = count_side_effect

    result = await handler.get_sync_status(GetSyncStatusQuery())

    assert len(result) == 2
    # Row 0 (5m) failed → fell back to sync_status
    assert result[0].interval == "5m"
    assert result[0].bar_count == 10  # sync_status fallback
    # Row 1 (15m) succeeded
    assert result[1].interval == "15m"
    assert result[1].bar_count == 999


@pytest.mark.asyncio
async def test_empty_status_list_returns_empty(handler, sync_status_repo, bar_repo) -> None:
    sync_status_repo.find_all.return_value = []
    result = await handler.get_sync_status(GetSyncStatusQuery())
    assert result == []
    bar_repo.get_latest.assert_not_called()
    bar_repo.count.assert_not_called()


@pytest.mark.asyncio
async def test_last_sync_at_still_from_sync_status(handler, sync_status_repo, bar_repo) -> None:
    """last_sync_at is COMMAND-log field; should remain from sync_status, not bars."""
    sync_dt = NOW - timedelta(hours=2)
    s = _status("5m", last_bar_age_seconds=60)
    s.last_sync_at = sync_dt
    sync_status_repo.find_all.return_value = [s]
    bar_repo.get_latest.return_value = _bar(NOW - timedelta(seconds=60), Interval.MINUTE_5)
    bar_repo.count.return_value = 100

    result = await handler.get_sync_status(GetSyncStatusQuery())

    assert result[0].last_sync_at == sync_dt.isoformat().replace("+00:00", "Z")


# get_symbol_sync_status — single symbol/interval lookup


@pytest.mark.asyncio
async def test_returns_is_stuck_field_populated(handler, sync_status_repo, bar_repo) -> None:
    """Previously the handler did not populate is_stuck (defaulted False).
    Now should reflect actual bar freshness."""
    sync_status_repo.find_one.return_value = _status("5m", last_bar_age_seconds=3600)
    bar_repo.get_latest.return_value = _bar(NOW - timedelta(seconds=2000), Interval.MINUTE_5)
    bar_repo.count.return_value = 100

    result = await handler.get_symbol_sync_status(
        GetSymbolSyncStatusQuery(symbol=SYMBOL, interval="5m"),
    )

    # 5m cadence 300s × 3 = 900s; bar age 2000s > 900s → stuck
    assert result.is_stuck is True


@pytest.mark.asyncio
async def test_uses_bars_for_count_and_last_bar(handler, sync_status_repo, bar_repo) -> None:
    """bar_count and last_bar_at come from bars, not sync_status."""
    fresh_dt = NOW - timedelta(seconds=60)
    sync_status_repo.find_one.return_value = _status("1h", last_bar_age_seconds=7200, bar_count=999)
    bar_repo.get_latest.return_value = _bar(fresh_dt, Interval.HOUR_1)
    bar_repo.count.return_value = 5907

    result = await handler.get_symbol_sync_status(
        GetSymbolSyncStatusQuery(symbol=SYMBOL, interval="1h"),
    )

    assert result.bar_count == 5907  # ← bars
    assert result.last_bar_at == fresh_dt.isoformat().replace("+00:00", "Z")
    assert result.is_stuck is False


@pytest.mark.asyncio
async def test_not_found_raises(handler, sync_status_repo, bar_repo) -> None:
    """If sync_status row missing, NotFoundError as before."""
    sync_status_repo.find_one.return_value = None

    with pytest.raises(NotFoundError):
        await handler.get_symbol_sync_status(
            GetSymbolSyncStatusQuery(symbol=SYMBOL, interval="5m"),
        )

    bar_repo.get_latest.assert_not_called()
    bar_repo.count.assert_not_called()


@pytest.mark.asyncio
async def test_no_bars_yet_returns_not_stuck_single_symbol(
    handler,
    sync_status_repo,
    bar_repo,
) -> None:
    sync_status_repo.find_one.return_value = _status("5m", last_bar_age_seconds=60)
    bar_repo.get_latest.return_value = None
    bar_repo.count.return_value = 0

    result = await handler.get_symbol_sync_status(
        GetSymbolSyncStatusQuery(symbol=SYMBOL, interval="5m"),
    )

    assert result.is_stuck is False
    assert result.bar_count == 0
    assert result.last_bar_at is None


@pytest.mark.asyncio
async def test_status_and_error_from_sync_status(handler, sync_status_repo, bar_repo) -> None:
    """status/error_message are command-log fields; come from sync_status."""
    s = _status("5m", last_bar_age_seconds=60)
    s.status = "error"
    s.error_message = "TV REST timeout"
    sync_status_repo.find_one.return_value = s
    bar_repo.get_latest.return_value = _bar(NOW - timedelta(seconds=60), Interval.MINUTE_5)
    bar_repo.count.return_value = 100

    result = await handler.get_symbol_sync_status(
        GetSymbolSyncStatusQuery(symbol=SYMBOL, interval="5m"),
    )

    assert result.status == "error"
    assert result.error_message == "TV REST timeout"
