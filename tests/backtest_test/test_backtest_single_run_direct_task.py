"""Direct-task single-run — started doc, shared run_id, fail-by-inspect, sweep.

Exercises the phase-2 trigger path (BacktestCommandService.run save-started +
BacktestExecutionService.execute_and_persist) end to end against real repos, the
slice the characterization test (engine-only) doesn't cover.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest

from pocketquant.backtest.backtest_command_service import (
    BacktestCommandService,
    RunBacktestCommand,
)
from pocketquant.backtest.backtest_execution_service import BacktestExecutionService
from pocketquant.backtest.workers.backtest_dispatch import BacktestDispatchDeps
from pocketquant.core.common.time.simulation import clear_simulation_time
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.backtest_order_repository import (
    BacktestOrderRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_trade_repository import (
    BacktestTradeRepository,
)
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository

_SYM = "BTCUSDT:BINANCE"
_T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _reset_sim_time() -> Generator[None]:
    clear_simulation_time()
    yield
    clear_simulation_time()


def _bar(idx: int, *, o: float, h: float, lo: float, c: float) -> Bar:
    return Bar(
        symbol=_SYM,
        interval=Interval.MINUTE_1,
        datetime=_T0 + timedelta(minutes=idx),
        open=o,
        high=h,
        low=lo,
        close=c,
        volume=1.0,
        tick_count=1,
    )


def _flat(idx: int) -> Bar:
    return _bar(idx, o=100.0, h=100.2, lo=99.8, c=100.0)


def _engulfing_bars(cycles: int = 2, lookback: int = 5) -> list[Bar]:
    bars: list[Bar] = []
    idx = 0
    for _ in range(lookback + 1):
        bars.append(_flat(idx))
        idx += 1
    for _ in range(cycles):
        bars.append(_bar(idx, o=100.5, h=100.6, lo=99.4, c=99.5))
        idx += 1
        bars.append(_bar(idx, o=99.4, h=101.1, lo=99.3, c=101.0))
        idx += 1
        bars.append(_bar(idx, o=101.0, h=103.0, lo=100.5, c=102.5))
        idx += 1
        for _ in range(lookback + 1):
            bars.append(_flat(idx))
            idx += 1
    return bars


async def _seed_bars(database: Database, bars: list[Bar]) -> None:
    coll = database.get_collection("bars")
    await coll.delete_many({"symbol": _SYM, "interval": Interval.MINUTE_1.value})
    await coll.insert_many([b.to_mongo() for b in bars])


def _deps(database: Database) -> BacktestDispatchDeps:
    """run_single builds its own isolated sandbox, so deps is just the repos."""
    return BacktestDispatchDeps(
        bar_repo=BarRepository(database),
        backtest_repo=BacktestRepository(database),
        order_repo=BacktestOrderRepository(database),
        trade_repo=BacktestTradeRepository(database),
    )


def _cmd_svc(database: Database) -> BacktestCommandService:
    return BacktestCommandService(backtest_repository=BacktestRepository(database))


def _command(**overrides) -> RunBacktestCommand:
    base = {
        "strategy_id": "engulfing",
        "symbol": _SYM,
        "interval": "1m",
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        "initial_capital": 10_000.0,
        "slippage_bps": 0.0,
        "commission_bps": 0.0,
        "parameters": {"direction": "long", "key_level_lookback_bars": 5},
    }
    base.update(overrides)
    return RunBacktestCommand(**base)


@pytest.mark.asyncio
async def test_run_saves_started_doc_then_execute_finishes_same_run_id(
    database: Database,
) -> None:
    await _seed_bars(database, _engulfing_bars())
    backtest_repo = BacktestRepository(database)

    run_id, config = await _cmd_svc(database).run(_command())

    # M1 — started doc exists immediately, round-trips from_mongo, zeroed metrics.
    started = await backtest_repo.get(run_id)
    assert started is not None
    assert started.status == "started"
    assert started.metrics.total_trades == 0
    assert started.equity_curve == []

    await BacktestExecutionService(_deps(database), backtest_repo).execute_and_persist(
        run_id, config
    )

    # C2 — same id flips started → finished with real metrics + persisted children.
    finished = await backtest_repo.get(run_id)
    assert finished is not None
    assert finished.status == "finished"
    orders = await BacktestOrderRepository(database).list_by_run(run_id)
    trades = await BacktestTradeRepository(database).list_by_run(run_id)
    assert all(o.run_id == run_id for o in orders)
    assert all(t.run_id == run_id for t in trades)


@pytest.mark.asyncio
async def test_engine_failure_marks_failed_via_inspect_not_exception(
    database: Database,
) -> None:
    """C1 — engine returns a failed result (no raise); doc still ends ``failed``."""
    await _seed_bars(database, _engulfing_bars())
    backtest_repo = BacktestRepository(database)

    # Unknown strategy → engine path raises inside run_single BEFORE the engine's
    # own try/except, surfacing through execute_and_persist's outer guard.
    assert "definitely-not-a-strategy" not in STRATEGY_REGISTRY
    run_id, config = await _cmd_svc(database).run(
        _command(strategy_id="definitely-not-a-strategy")
    )
    await BacktestExecutionService(_deps(database), backtest_repo).execute_and_persist(
        run_id, config
    )

    failed = await backtest_repo.get(run_id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.error_message


@pytest.mark.asyncio
async def test_orphan_started_swept_to_failed_on_boot(database: Database) -> None:
    """M2 — a run left ``started`` by a killed task is flipped on the next boot."""
    backtest_repo = BacktestRepository(database)
    run_id, _ = await _cmd_svc(database).run(_command())

    n = await backtest_repo.mark_orphaned_started_as_failed()
    assert n == 1

    swept = await backtest_repo.get(run_id)
    assert swept is not None
    assert swept.status == "failed"
    assert swept.error_message == "interrupted_by_restart"
