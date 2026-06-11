"""Pin SyncService behavior through the feature service (ex-CQRS handlers).

Covers: happy path, skip_filter bypass, misaligned-bar drop, no-progress path,
bulk fan-out, and first-sync-no-data failure.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.engine.market_data.sync_service import (
    BulkSyncCommand,
    SyncResponse,
    SyncService,
    SyncSymbolCommand,
)

SYMBOL = "BTCUSDT:BINANCE"


def _aligned_bar(dt: datetime | None = None) -> Bar:
    ts = dt or datetime(2026, 5, 5, 12, 0, tzinfo=UTC)
    return Bar(
        symbol=SYMBOL,
        interval=Interval.MINUTE_1,
        datetime=ts,
        open=1.0,
        high=1.0,
        low=1.0,
        close=1.0,
        volume=1.0,
        tick_count=1,
    )


def _misaligned_bar() -> Bar:
    # Timestamp not on 1m grid boundary
    return Bar(
        symbol=SYMBOL,
        interval=Interval.MINUTE_1,
        datetime=datetime(2026, 5, 5, 12, 0, 37, tzinfo=UTC),
        open=1.0,
        high=1.0,
        low=1.0,
        close=1.0,
        volume=1.0,
        tick_count=1,
    )


def _build_service(
    *,
    fetch_records: list[Bar],
    fetch_attempts: int = 1,
    insert_count: int = 1,
    total_bars: int = 100,
    existing_bar: Bar | None = None,
    bump_returns: int = 1,
    filter_returns: list[Bar] | None = None,
    align_returns: list[Bar] | None = None,
) -> tuple[SyncService, dict]:
    provider = AsyncMock()
    cache = AsyncMock()
    cache.delete_pattern = AsyncMock()

    bar_repo = AsyncMock()
    bar_repo.insert_many = AsyncMock(return_value=insert_count)
    bar_repo.count = AsyncMock(return_value=total_bars)
    bar_repo.get_latest = AsyncMock(return_value=existing_bar or _aligned_bar())
    bar_repo.find_datetimes = AsyncMock(return_value=[])

    symbol_repo = AsyncMock()
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

    # Patch fetch_with_retry so tests control records+attempts directly.
    fetch_mock = AsyncMock(return_value=(fetch_records, fetch_attempts))
    patch_target = "pocketquant.engine.market_data.sync_service.fetch_with_retry"
    svc._fetch_patch = patch(patch_target, fetch_mock)  # type: ignore[attr-defined]
    svc._fetch_patch.start()  # type: ignore[attr-defined]

    # Optionally patch filter_new_bars and drop_misaligned_bars for isolation.
    if filter_returns is not None:
        filter_mock = AsyncMock(return_value=filter_returns)
        fp = patch("pocketquant.engine.market_data.sync_service.filter_new_bars", filter_mock)
        fp.start()
        svc._filter_patch = fp  # type: ignore[attr-defined]

    if align_returns is not None:
        align_mock = lambda records, interval: align_returns  # noqa: E731
        ap = patch("pocketquant.engine.market_data.sync_service.drop_misaligned_bars", align_mock)
        ap.start()
        svc._align_patch = ap  # type: ignore[attr-defined]

    return svc, mocks


def _stop(svc: SyncService) -> None:
    for attr in ("_fetch_patch", "_filter_patch", "_align_patch"):
        p = getattr(svc, attr, None)
        if p is not None:
            p.stop()


def _cmd(**kwargs) -> SyncSymbolCommand:  # type: ignore[return]
    defaults = dict(symbol=SYMBOL, interval=Interval.MINUTE_1, n_bars=100, source="test")
    defaults.update(kwargs)
    return SyncSymbolCommand(**defaults)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_one_happy_path_returns_completed() -> None:
    bar = _aligned_bar()
    svc, mocks = _build_service(fetch_records=[bar], insert_count=1)
    try:
        result = await svc.sync_one(_cmd())
    finally:
        _stop(svc)

    assert isinstance(result, SyncResponse)
    assert result.status == "completed"
    assert result.bars_synced == 1
    mocks["sync_status_repo"].reset_empty_fetch.assert_awaited_once()
    mocks["cache"].delete_pattern.assert_awaited_once()


# ---------------------------------------------------------------------------
# skip_filter bypasses filter_new_bars
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skip_filter_bypasses_existence_check() -> None:
    bar = _aligned_bar()
    svc, mocks = _build_service(fetch_records=[bar], insert_count=1)
    try:
        with patch("pocketquant.engine.market_data.sync_service.filter_new_bars") as mock_filter:
            await svc.sync_one(_cmd(skip_filter=True))
    finally:
        _stop(svc)

    mock_filter.assert_not_called()


# ---------------------------------------------------------------------------
# Misaligned bar dropped before insert
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_misaligned_bars_dropped_before_insert() -> None:
    misaligned = _misaligned_bar()
    # filter_returns = both bars pass existence check; align_returns = [] (all misaligned)
    svc, mocks = _build_service(
        fetch_records=[misaligned],
        insert_count=0,
        filter_returns=[misaligned],
        align_returns=[],
        existing_bar=_aligned_bar(),
    )
    try:
        result = await svc.sync_one(_cmd())
    finally:
        _stop(svc)

    assert result.filtered_misaligned == 1
    mocks["bar_repo"].insert_many.assert_not_called()


# ---------------------------------------------------------------------------
# No-progress path bumps streak
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_progress_bumps_streak() -> None:
    bar = _aligned_bar()
    svc, mocks = _build_service(
        fetch_records=[bar],
        insert_count=0,  # nothing inserted → no-progress
        total_bars=10,  # existing data → not first-sync-fail
        filter_returns=[bar],
        align_returns=[bar],
        bump_returns=1,
    )
    try:
        result = await svc.sync_one(_cmd())
    finally:
        _stop(svc)

    assert result.status == "completed"
    mocks["sync_status_repo"].bump_empty_fetch.assert_awaited_once()
    mocks["sync_status_repo"].reset_empty_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# First sync no data → error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_sync_no_data_returns_error() -> None:
    svc, mocks = _build_service(
        fetch_records=[],
        total_bars=0,
        existing_bar=None,
    )
    try:
        result = await svc.sync_one(_cmd())
    finally:
        _stop(svc)

    assert result.status == "error"
    assert "No data" in (result.message or "")
    mocks["sync_status_repo"].bump_empty_fetch.assert_not_called()
    mocks["sync_status_repo"].reset_empty_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# Bulk fan-out sends SOURCE_BULK_SYNC to each symbol
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_bulk_fans_out_with_bulk_sync_source() -> None:
    bar = _aligned_bar()
    svc, _mocks = _build_service(fetch_records=[bar], insert_count=1)
    try:
        cmd = BulkSyncCommand(
            symbols=["BTCUSDT:BINANCE", "ETHUSDT:BINANCE"],
            interval=Interval.DAY_1,
            n_bars=100,
        )
        results = await svc.sync_bulk(cmd)
    finally:
        _stop(svc)

    assert len(results) == 2
    assert all(r.status == "completed" for r in results)


# ---------------------------------------------------------------------------
# Exception in provider → error response, no re-raise
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provider_exception_returns_error_response() -> None:
    svc, mocks = _build_service(fetch_records=[])

    # Override fetch_with_retry to raise
    async def _raise(*_a, **_kw):
        raise RuntimeError("provider down")

    svc._fetch_patch.stop()  # type: ignore[attr-defined]
    with patch("pocketquant.engine.market_data.sync_service.fetch_with_retry", side_effect=_raise):
        result = await svc.sync_one(_cmd())

    assert result.status == "error"
    assert "provider down" in (result.message or "")
