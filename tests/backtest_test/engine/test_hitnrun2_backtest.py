from __future__ import annotations

import math
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest

from pocketquant.core.common.constants import COLLECTION_BARS, COLLECTION_SYMBOLS
from pocketquant.core.common.time.simulation import clear_simulation_time
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.symbol import ContractSpec, Symbol
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

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


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


# A 30-bar sine keeps the previous trough inside the 40-bar SL window, so breakdowns have
# a stop on the right side.
def _series(symbol: str) -> list[Bar]:
    step = timedelta(minutes=1)
    bars: list[Bar] = []
    prev = 100.0
    for k in range(int(timedelta(days=2) / step)):
        close = 100 + 10 * math.sin(2 * math.pi * k / 30)
        bars.append(
            Bar(
                symbol=symbol,
                interval=Interval("1m"),
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


async def _clear(database: Database, symbol: str) -> None:
    await database.get_collection(COLLECTION_BARS).delete_many({"symbol": symbol})
    await database.get_collection(COLLECTION_SYMBOLS).delete_many({"symbol": symbol})


# The nearer exit is at most max_loss_pct of about 100, near 1.0, below 3 x 2.0, so the
# costly spec must skip every entry. Distinct symbols avoid the 60 s symbol lookup cache.
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("symbol", "spec", "any_trades"),
    [
        ("HNRFREE:BINANCE", ContractSpec(), True),
        ("HNRDEAR:BINANCE", ContractSpec(commission_per_contract=1.0), False),
    ],
)
async def test_the_backtest_filter_reads_the_symbol_spec(
    database: Database, symbol: str, spec: ContractSpec, any_trades: bool
) -> None:
    await _clear(database, symbol)
    try:
        await SymbolRepository(database).upsert(Symbol.create(symbol, contract_spec=spec))
        await database.get_collection(COLLECTION_BARS).insert_many(
            [b.to_mongo() for b in _series(symbol)]
        )

        run_id, config = await _cmd_svc(database).run(
            RunBacktestCommand(
                strategy_id="hitnrun2",
                symbol=symbol,
                intervals=["1m"],
                start_date=_T0 + timedelta(days=1),
                end_date=_T0 + timedelta(days=2),
                slippage_bps=0,
                commission_bps=0,
                parameters={
                    "entry_lookback_bars": 20,
                    "sl_lookback_bars": 40,
                    "tp_lookback_bars": 10,
                    "min_profit_pct": 0.0,
                },
            )
        )
        await _execution(database).execute_and_persist(run_id, config)

        run = await BacktestRepository(database).get(run_id)
        assert run is not None
        assert run.status == "finished"
        if any_trades:
            assert run.metrics.total_trades >= 1
        else:
            assert run.metrics.total_trades == 0
    finally:
        await _clear(database, symbol)
