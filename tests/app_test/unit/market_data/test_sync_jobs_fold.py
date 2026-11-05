from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pocketquant.core.domain.shared.enums import Interval
from pocketquant.engine.market_data.app_services import sync_jobs
from pocketquant.engine.market_data.sync_service import SyncService
from tests.app_test.unit.market_data.test_sync_jobs_tracked import _wire


@pytest.mark.asyncio
async def test_repair_folds_seven_days_for_every_symbol_even_after_one_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = _wire(monkeypatch, MagicMock(spec=SyncService), doc_id="hist-1")

    async def repair(symbol, interval, bar_repo, sync_service, calendar, **kwargs):  # noqa: ANN001
        if symbol == "BTCUSDT:BINANCE":
            raise RuntimeError("bad data")
        return {"deleted": 0, "gaps_resynced": 0}

    cascade = AsyncMock(return_value={})
    monkeypatch.setattr(sync_jobs, "repair_integrity", repair)
    monkeypatch.setattr(sync_jobs, "cascade_for_symbol", cascade)

    await sync_jobs.sync_repair()

    assert [c.args[0] for c in cascade.await_args_list] == ["BTCUSDT:BINANCE", "ETHUSDT:BINANCE"]
    assert {c.kwargs["lookback_minutes"] for c in cascade.await_args_list} == {10080}
    finish = history.record_finish.await_args.kwargs
    assert finish["status"] == "failed"
    assert finish["error"] == "1 of 2 symbols failed"


@pytest.mark.asyncio
async def test_repair_fetches_only_the_intervals_the_cascade_cannot_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire(monkeypatch, MagicMock(spec=SyncService), doc_id="hist-1")
    calls: list[Interval] = []

    async def repair(symbol, interval, bar_repo, sync_service, calendar, *, source):  # noqa: ANN001
        calls.append(interval)
        return {"deleted": 0, "gaps_resynced": 0}

    monkeypatch.setattr(sync_jobs, "repair_integrity", repair)
    monkeypatch.setattr(sync_jobs, "cascade_for_symbol", AsyncMock(return_value={}))

    await sync_jobs.sync_repair()

    assert set(calls) == {Interval.MINUTE_1, Interval.WEEK_1}


@pytest.mark.asyncio
async def test_backfill_folds_after_the_rest_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire(monkeypatch, MagicMock(spec=SyncService), doc_id="hist-1")
    order: list[str] = []

    async def rest_sync(*args, **kwargs):  # noqa: ANN002, ANN003
        order.append("rest")
        return {"total_inserted": 0, "total_fetched": 0}

    async def cascade(symbol, **kwargs):  # noqa: ANN001, ANN003
        order.append(f"cascade:{symbol}:{kwargs['lookback_minutes']}")
        return {}

    monkeypatch.setattr(sync_jobs, "_rest_sync", rest_sync)
    monkeypatch.setattr(sync_jobs, "cascade_for_symbol", cascade)

    await sync_jobs.sync_backfill()

    assert order == [
        "rest",
        "cascade:BTCUSDT:BINANCE:10080",
        "cascade:ETHUSDT:BINANCE:10080",
    ]
