"""Job-history wrapper: a failed run is recorded once and never stops the rest."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.infra.persistence.repositories.job_history_repository import (
    JobHistoryRepository,
)
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)
from pocketquant.engine.market_data.app_services import sync_jobs
from pocketquant.engine.market_data.sync_service import SyncService


class _Container:
    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    async def get(self, cls):  # noqa: ANN001
        return self._mapping[cls]


def _wire(monkeypatch: pytest.MonkeyPatch, sync_service: MagicMock, *, doc_id: str | None):
    tracked = []
    for symbol in ("BTCUSDT:BINANCE", "ETHUSDT:BINANCE"):
        ts = MagicMock()
        ts.symbol = symbol
        tracked.append(ts)
    tracked_repo = MagicMock()
    tracked_repo.list_all = AsyncMock(return_value=tracked)

    history = MagicMock()
    history.record_start = AsyncMock(return_value=doc_id)
    if doc_id is None:
        history.record_start.side_effect = RuntimeError("mongo down")
    history.record_detail = AsyncMock()
    history.record_finish = AsyncMock()

    factory = MagicMock()
    factory.for_symbol = AsyncMock(return_value=Continuous24x7Calendar())

    container = _Container(
        {
            JobHistoryRepository: history,
            SyncService: sync_service,
            TrackedSymbolRepository: tracked_repo,
            BarRepository: MagicMock(),
            TradingCalendarFactory: factory,
        }
    )
    monkeypatch.setattr(sync_jobs, "_container", container)
    return history


def _failing_sync() -> MagicMock:
    svc = MagicMock(spec=SyncService)
    svc.sync_one = AsyncMock(side_effect=RuntimeError("provider down"))
    return svc


@pytest.mark.asyncio
async def test_a_failed_rest_sync_still_cascades_and_is_recorded_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = _wire(monkeypatch, _failing_sync(), doc_id="hist-1")
    cascade = AsyncMock(return_value={})
    monkeypatch.setattr(sync_jobs, "cascade_for_symbol", cascade)

    await sync_jobs.sync_1m()  # not re-raised: the scheduler hook would record it again

    assert cascade.await_count == 2
    history.record_finish.assert_awaited_once()
    finish = history.record_finish.await_args.kwargs
    assert finish["status"] == "failed"
    assert finish["error"] == "provider down"


@pytest.mark.asyncio
async def test_without_a_start_record_the_error_reaches_the_scheduler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = _wire(monkeypatch, _failing_sync(), doc_id=None)

    with pytest.raises(RuntimeError, match="provider down"):
        await sync_jobs.sync_backfill()

    history.record_finish.assert_not_awaited()


@pytest.mark.asyncio
async def test_one_failing_symbol_does_not_stop_integrity_for_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = _wire(monkeypatch, MagicMock(spec=SyncService), doc_id="hist-1")
    seen: list[str] = []

    async def check(symbol, interval, bar_repo, calendar):  # noqa: ANN001
        seen.append(symbol)
        if symbol == "BTCUSDT:BINANCE":
            raise RuntimeError("bad data")
        return {"misaligned_count": 0, "missing_count": 0}

    monkeypatch.setattr(sync_jobs, "check_integrity", check)

    await sync_jobs.sync_integrity()

    assert "ETHUSDT:BINANCE" in seen
    finish = history.record_finish.await_args.kwargs
    assert finish["status"] == "failed"
    assert finish["error"] == "1 of 2 symbols failed"
