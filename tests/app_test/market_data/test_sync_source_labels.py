"""Tests asserting source/provenance labels propagate through cascade, repair, and sync jobs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from pocketquant.core.domain.bar.entities import (
    SOURCE_CASCADE,
    SOURCE_REST_BACKFILL,
    SOURCE_REST_REPAIR,
    SOURCE_REST_SYNC_1M,
    Bar,
)
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.engine.market_data.app_services import sync_jobs
from pocketquant.engine.market_data.app_services.cascade_aggregator import cascade_for_symbol
from pocketquant.engine.market_data.app_services.integrity_jobs import repair_integrity
from pocketquant.engine.market_data.sync_service import SyncService, SyncSymbolCommand

# cascade_for_symbol passes source=SOURCE_CASCADE on every upsert_bar call


def _make_1m_bars(n: int = 60) -> list[Bar]:
    base = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    return [
        Bar(
            symbol="BTCUSDT:BINANCE",
            interval=Interval.MINUTE_1,
            datetime=base + timedelta(minutes=i),
            open=1.0,
            high=2.0,
            low=0.5,
            close=1.5,
            volume=10.0,
            tick_count=1,
        )
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_cascade_for_symbol_passes_source_cascade() -> None:
    bar_repo = AsyncMock()
    bar_repo.find = AsyncMock(return_value=_make_1m_bars(60))
    bar_repo.upsert_bar = AsyncMock()

    await cascade_for_symbol(
        symbol="BTCUSDT:BINANCE",
        lookback_minutes=60,
        bar_repo=bar_repo,
    )

    assert bar_repo.upsert_bar.await_count > 0
    for call in bar_repo.upsert_bar.await_args_list:
        assert call.kwargs.get("source") == SOURCE_CASCADE


# repair_integrity forwards source kwarg into the SyncSymbolCommand it calls on SyncService


@pytest.mark.asyncio
async def test_repair_integrity_sends_command_with_source() -> None:
    bar_repo = MagicMock()
    bar_repo.find_datetimes = AsyncMock(return_value=[])
    bar_repo.delete_many_by_ids = AsyncMock(return_value=0)

    sync_service = MagicMock(spec=SyncService)
    sync_service.sync_one = AsyncMock()

    # Force a "gap" so the resync command is built and dispatched.
    async def fake_find_datetimes(*_a, **_kw):
        return []

    # Patch check_integrity result indirectly: by having no docs AND a wide gap.
    # repair_integrity calls check_integrity which reads find_datetimes; empty list
    # → full window is a gap. Force the path that builds + sends the command.
    bar_repo.find_datetimes = AsyncMock(side_effect=fake_find_datetimes)

    result = await repair_integrity(
        symbol="BTCUSDT:BINANCE",
        interval=Interval.MINUTE_1,
        bar_repo=bar_repo,
        sync_service=sync_service,
        source=SOURCE_REST_REPAIR,
        days_back=1,
    )

    # sync_service.sync_one must have been called with a SyncSymbolCommand carrying source.
    assert sync_service.sync_one.await_count >= 1
    sent_cmd = sync_service.sync_one.await_args.args[0]
    assert isinstance(sent_cmd, SyncSymbolCommand)
    assert sent_cmd.source == SOURCE_REST_REPAIR
    assert sent_cmd.skip_filter is True
    assert "gaps_resynced" in result


# sync_1m and sync_backfill hand-off the correct source label to SyncService


class _FakeContainer:
    """Minimal Dishka-like container for sync_jobs tests."""

    def __init__(self, mapping: dict):
        self._mapping = mapping

    async def get(self, cls):
        return self._mapping[cls]


def _wire_container(monkeypatch: pytest.MonkeyPatch, *, sync_service) -> None:
    from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
    from pocketquant.core.infra.persistence.repositories.job_history_repository import (
        JobHistoryRepository,
    )
    from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
        TrackedSymbolRepository,
    )

    tracked_repo = MagicMock()
    # one tracked symbol triggers one sync_service.sync_one per interval.
    tracked_sym = MagicMock()
    tracked_sym.symbol = "BTCUSDT:BINANCE"
    tracked_repo.list_all = AsyncMock(return_value=[tracked_sym])

    history_repo = MagicMock()
    history_repo.record_start = AsyncMock(return_value="hist-1")
    history_repo.record_detail = AsyncMock()
    history_repo.record_finish = AsyncMock()

    bar_repo = MagicMock()

    container = _FakeContainer(
        {
            SyncService: sync_service,
            JobHistoryRepository: history_repo,
            TrackedSymbolRepository: tracked_repo,
            BarRepository: bar_repo,
        }
    )
    monkeypatch.setattr(sync_jobs, "_container", container)


def _make_sync_service() -> MagicMock:
    svc = MagicMock(spec=SyncService)
    result = MagicMock()
    result.bars_synced = 0
    result.bars_fetched = 0
    result.filtered_existing = 0
    result.filtered_misaligned = 0
    result.status = "completed"
    result.message = ""
    svc.sync_one = AsyncMock(return_value=result)
    return svc


@pytest.mark.asyncio
async def test_sync_1m_dispatches_with_rest_sync_1m_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_service = _make_sync_service()
    _wire_container(monkeypatch, sync_service=sync_service)

    # Stub cascade_for_symbol to avoid touching bar repo.
    monkeypatch.setattr(
        sync_jobs,
        "cascade_for_symbol",
        AsyncMock(return_value={}),
    )

    await sync_jobs.sync_1m()

    sent = [c.args[0] for c in sync_service.sync_one.await_args_list]
    assert any(isinstance(s, SyncSymbolCommand) for s in sent)
    for cmd in sent:
        assert cmd.source == SOURCE_REST_SYNC_1M


@pytest.mark.asyncio
async def test_sync_backfill_dispatches_with_rest_backfill_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_service = _make_sync_service()
    _wire_container(monkeypatch, sync_service=sync_service)

    await sync_jobs.sync_backfill()

    sent = [c.args[0] for c in sync_service.sync_one.await_args_list]
    assert sent, "expected at least one SyncSymbolCommand dispatched"
    for cmd in sent:
        assert cmd.source == SOURCE_REST_BACKFILL


# SyncSymbolCommand.source accepts arbitrary/custom provenance labels


def test_source_accepts_arbitrary_string() -> None:
    cmd = SyncSymbolCommand(
        symbol="BTCUSDT:BINANCE",
        interval=Interval.MINUTE_1,
        source="rest_sync_1m",
    )
    assert cmd.source == "rest_sync_1m"


def test_source_accepts_custom_label() -> None:
    cmd = SyncSymbolCommand(
        symbol="BTCUSDT:BINANCE",
        interval=Interval.MINUTE_1,
        source="my_label",
    )
    assert cmd.source == "my_label"
