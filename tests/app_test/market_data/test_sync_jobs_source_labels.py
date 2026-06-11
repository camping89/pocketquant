"""sync_1m and sync_backfill hand-off the correct source label to SyncService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pocketquant.core.domain.bar.entities import (
    SOURCE_REST_BACKFILL,
    SOURCE_REST_SYNC_1M,
)
from pocketquant.engine.market_data.app_services import sync_jobs
from pocketquant.engine.market_data.sync_service import SyncService, SyncSymbolCommand


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
