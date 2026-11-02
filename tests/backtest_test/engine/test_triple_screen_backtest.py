from __future__ import annotations

import math
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest

from pocketquant.core.common.constants import COLLECTION_BARS, INTERVAL_SECONDS
from pocketquant.core.common.time.simulation import clear_simulation_time
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
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
from pocketquant.core.infra.persistence.repositories.symbol_repository import SymbolRepository
from pocketquant.core.infra.persistence.symbol_lookup_helper import SymbolLookupHelper
from pocketquant.engine.backtest.backtest_command_service import (
    BacktestCommandService,
    RunBacktestCommand,
)
from pocketquant.engine.backtest.backtest_execution_service import BacktestExecutionService

_SYM = "BTCUSDT:BINANCE"
_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_DAYS = 30
_INTERVALS = ["15m", "1h", "4h"]


@pytest.fixture(autouse=True)
def _reset_sim_time() -> Generator[None]:
    clear_simulation_time()
    yield
    clear_simulation_time()


def _execution(database: Database) -> BacktestExecutionService:
    symbol_lookup = SymbolLookupHelper(SymbolRepository(database))
    return BacktestExecutionService(
        bar_repository=BarRepository(database),
        backtest_repository=BacktestRepository(database),
        backtest_order_repository=BacktestOrderRepository(database),
        backtest_trade_repository=BacktestTradeRepository(database),
        calendar_factory=TradingCalendarFactory(symbol_lookup),
        symbol_lookup=symbol_lookup,
    )


def _cmd_svc(database: Database) -> BacktestCommandService:
    return BacktestCommandService(backtest_repository=BacktestRepository(database))


def _top(i: int) -> float:
    return 100 + 10 * math.sin(2 * math.pi * i / 30)


def _close(interval: str, k: int) -> float:
    if interval == "4h":
        return _top(k)
    if interval == "1h":
        return _top(k // 4) + 0.5 * math.sin(2 * math.pi * k / 6)
    return 100 + 10 * math.sin(2 * math.pi * k / 480) + 0.3 * math.sin(2 * math.pi * k / 7)


def _series(interval: str) -> list[Bar]:
    step = timedelta(seconds=INTERVAL_SECONDS[interval])
    bars: list[Bar] = []
    prev = _close(interval, 0)
    for k in range(int(timedelta(days=_DAYS) / step)):
        close = _close(interval, k)
        bars.append(
            Bar(
                symbol=_SYM,
                interval=Interval(interval),
                datetime=_T0 + k * step,
                open=prev,
                high=max(prev, close) + 0.2,
                low=min(prev, close) - 0.2,
                close=close,
                volume=1.0,
                tick_count=1,
            )
        )
        prev = close
    return bars


async def _clear_bars(database: Database) -> None:
    await database.get_collection(COLLECTION_BARS).delete_many(
        {"symbol": _SYM, "interval": {"$in": _INTERVALS}}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "parameters",
    [
        {"entry_type": "market", "exit_mode": "sl_tp"},
        {"entry_type": "stop", "exit_mode": "strategy"},
    ],
)
async def test_triple_screen_backtest_finishes_with_trades(
    database: Database, parameters: dict
) -> None:
    await _clear_bars(database)
    try:
        coll = database.get_collection(COLLECTION_BARS)
        for interval in _INTERVALS:
            await coll.insert_many([b.to_mongo() for b in _series(interval)])

        run_id, config = await _cmd_svc(database).run(
            RunBacktestCommand(
                strategy_id="triple_screen",
                symbol=_SYM,
                intervals=_INTERVALS,
                start_date=_T0 + timedelta(days=7),
                end_date=_T0 + timedelta(days=_DAYS),
                slippage_bps=0,
                commission_bps=0,
                parameters=parameters,
            )
        )
        await _execution(database).execute_and_persist(run_id, config)

        run = await BacktestRepository(database).get(run_id)
        assert run is not None
        assert run.status == "finished"
        assert run.metrics.total_trades >= 1
    finally:
        await _clear_bars(database)
