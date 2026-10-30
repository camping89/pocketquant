from __future__ import annotations

import asyncio
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


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    sync_service: MagicMock,
    *,
    doc_id: str | None,
    resumed: tuple[str, set[str]] | None = None,
):
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
    history.resume_interrupted = AsyncMock(return_value=resumed)
    history.close_interrupted = AsyncMock()
    history.mark_symbol_done = AsyncMock()

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


# A stop cancels the task; the run ends interrupted and returns, so APScheduler logs
# no error.
@pytest.mark.asyncio
async def test_a_cancelled_sync_skips_the_cascade_and_ends_interrupted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = MagicMock(spec=SyncService)
    started = asyncio.Event()

    async def hang(command):  # noqa: ANN001
        started.set()
        await asyncio.Event().wait()

    svc.sync_one = AsyncMock(side_effect=hang)
    history = _wire(monkeypatch, svc, doc_id="hist-1")
    cascade = AsyncMock(return_value={})
    monkeypatch.setattr(sync_jobs, "cascade_for_symbol", cascade)

    job = asyncio.create_task(sync_jobs.sync_1m())
    await started.wait()
    job.cancel()
    await asyncio.wait([job])

    assert not job.cancelled()
    cascade.assert_not_awaited()
    assert history.record_finish.await_args.kwargs["status"] == "interrupted"
    history.resume_interrupted.assert_not_awaited()
    history.mark_symbol_done.assert_not_awaited()


# A CancelledError the task was not asked for is not a stop; it is not swallowed.
@pytest.mark.asyncio
async def test_a_stray_cancelled_error_is_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = MagicMock(spec=SyncService)
    svc.sync_one = AsyncMock(side_effect=asyncio.CancelledError())
    _wire(monkeypatch, svc, doc_id="hist-1")
    monkeypatch.setattr(sync_jobs, "cascade_for_symbol", AsyncMock(return_value={}))

    with pytest.raises(asyncio.CancelledError):
        await sync_jobs.sync_1m()


@pytest.mark.asyncio
async def test_a_cron_repair_starts_fresh_and_closes_cut_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = _wire(monkeypatch, MagicMock(spec=SyncService), doc_id="hist-1", resumed=("x", {"A"}))

    async def repair(symbol, interval, bar_repo, sync_service, calendar, source):  # noqa: ANN001
        return {"deleted": 0, "gaps_resynced": 0}

    monkeypatch.setattr(sync_jobs, "repair_integrity", repair)

    await sync_jobs.sync_repair()

    history.resume_interrupted.assert_not_awaited()
    history.close_interrupted.assert_awaited_once_with("sync_repair")
    history.record_start.assert_awaited_once_with("sync_repair")
    assert history.mark_symbol_done.await_count == 2


@pytest.mark.asyncio
async def test_a_second_run_of_a_running_job_returns_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = _wire(monkeypatch, MagicMock(spec=SyncService), doc_id="hist-1")
    gate = asyncio.Event()
    entered = asyncio.Event()

    async def repair(symbol, interval, bar_repo, sync_service, calendar, source):  # noqa: ANN001
        entered.set()
        await gate.wait()
        return {"deleted": 0, "gaps_resynced": 0}

    monkeypatch.setattr(sync_jobs, "repair_integrity", repair)
    first = asyncio.create_task(sync_jobs.sync_repair())
    await entered.wait()
    try:
        await sync_jobs.sync_repair(resume=True)
        history.resume_interrupted.assert_not_awaited()
        assert history.record_start.await_count == 1
    finally:
        gate.set()
        await first


@pytest.mark.asyncio
async def test_a_resumed_repair_runs_only_the_unfinished_symbols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = _wire(
        monkeypatch,
        MagicMock(spec=SyncService),
        doc_id="hist-new",
        resumed=("hist-cut", {"BTCUSDT:BINANCE"}),
    )
    seen: list[str] = []

    async def repair(symbol, interval, bar_repo, sync_service, calendar, source):  # noqa: ANN001
        seen.append(symbol)
        return {"deleted": 0, "gaps_resynced": 0}

    monkeypatch.setattr(sync_jobs, "repair_integrity", repair)

    await sync_jobs.sync_repair(resume=True)

    assert set(seen) == {"ETHUSDT:BINANCE"}
    history.record_start.assert_not_awaited()
    history.mark_symbol_done.assert_awaited_once_with("hist-cut", "ETHUSDT:BINANCE")
    finish = history.record_finish.await_args
    assert finish.args[0] == "hist-cut"
    assert finish.kwargs["status"] == "completed"


@pytest.mark.asyncio
async def test_a_backfill_marks_only_symbols_that_synced_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = MagicMock(spec=SyncService)

    async def sync_one(command):  # noqa: ANN001
        if command.symbol == "BTCUSDT:BINANCE":
            raise RuntimeError("provider down")
        return MagicMock(
            bars_synced=1,
            bars_fetched=1,
            filtered_existing=0,
            filtered_misaligned=0,
            status="completed",
            message=None,
        )

    svc.sync_one = AsyncMock(side_effect=sync_one)
    history = _wire(monkeypatch, svc, doc_id="hist-1")

    await sync_jobs.sync_backfill()

    history.mark_symbol_done.assert_awaited_once_with("hist-1", "ETHUSDT:BINANCE")
    assert history.record_finish.await_args.kwargs["status"] == "failed"


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
    history.mark_symbol_done.assert_awaited_once_with("hist-1", "ETHUSDT:BINANCE")
    finish = history.record_finish.await_args.kwargs
    assert finish["status"] == "failed"
    assert finish["error"] == "1 of 2 symbols failed"


# The worker stop cuts a repair after its first symbol; the row ends interrupted with
# that symbol marked, and the task ends cleanly.
@pytest.mark.asyncio
async def test_stop_running_jobs_cuts_a_repair_after_its_finished_symbols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = _wire(monkeypatch, MagicMock(spec=SyncService), doc_id="hist-1")
    second = asyncio.Event()

    async def repair(symbol, interval, bar_repo, sync_service, calendar, source):  # noqa: ANN001
        if symbol == "ETHUSDT:BINANCE":
            second.set()
            await asyncio.Event().wait()
        return {"deleted": 0, "gaps_resynced": 0}

    monkeypatch.setattr(sync_jobs, "repair_integrity", repair)
    job = asyncio.create_task(sync_jobs.sync_repair())
    await second.wait()

    assert await sync_jobs.stop_running_jobs(0.05) == 1

    assert job.done() and not job.cancelled()
    history.mark_symbol_done.assert_awaited_once_with("hist-1", "BTCUSDT:BINANCE")
    assert history.record_finish.await_args.kwargs["status"] == "interrupted"
