"""BacktestStatsService — paged trades (cursor roundtrip), markers, stats shape."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import NAMESPACE_OID, UUID, uuid5

import pytest

from pocketquant.backtest.backtest_stats_service import (
    BacktestStatsService,
    ListTradesQuery,
    TradeFilter,
    TradeSortDir,
    TradeSortKey,
)
from pocketquant.core.domain.backtest import BacktestResult
from pocketquant.core.domain.trading import EquityPoint, Trade
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_trade_repository import (
    BacktestTradeRepository,
)

T0 = datetime(2026, 1, 5, 10, 0, 0)
_RUN = "019f141c-a437-70a9-8d2a-d748b773d9e7"


def _tid(name: str) -> UUID:
    return uuid5(NAMESPACE_OID, name)


def _trade(name: str, *, pnl: float, direction: str = "LONG", hours: int = 0) -> Trade:
    return Trade(
        trade_id=_tid(name),
        run_id=_RUN,
        strategy_code="s1",
        symbol="BTCUSDT:BINANCE",
        direction=direction,
        entry_order_id="o-entry",
        entry_price=100.0,
        entry_time=T0 + timedelta(hours=hours),
        quantity=1.0,
        exit_order_id="o-exit",
        exit_price=100.0 + pnl,
        exit_time=T0 + timedelta(hours=hours + 1),
        sl_price=None,
        tp_price=None,
        pnl=pnl,
        commission=0.21,
        duration_seconds=3600.0,
    )


async def _seed_run(database: Database, *, equity_curve: list[EquityPoint] | None = None) -> None:
    repo = BacktestRepository(database)
    result = BacktestResult.started(_RUN, {"strategy_code": "s1", "symbol": "BTCUSDT:BINANCE"})
    result.status = "finished"
    if equity_curve is not None:
        result.equity_curve = equity_curve
    await repo.save(result)


@pytest.mark.asyncio
async def test_list_trades_paged_cursor_roundtrip(database: Database) -> None:
    trade_repo = BacktestTradeRepository(database)
    await trade_repo.save_many([_trade(f"t{i}", pnl=float(i), hours=i) for i in range(5)])
    svc = BacktestStatsService(BacktestRepository(database), trade_repo)

    page1 = await svc.list_trades_paged(
        ListTradesQuery(
            run_id=_RUN, limit=2, sort_key=TradeSortKey.entry_time, sort_dir=TradeSortDir.asc
        )
    )
    assert len(page1.items) == 2
    assert page1.has_more
    assert page1.next_cursor is not None
    assert page1.total == 5

    page2 = await svc.list_trades_paged(
        ListTradesQuery(
            run_id=_RUN,
            limit=2,
            cursor=page1.next_cursor,
            sort_key=TradeSortKey.entry_time,
            sort_dir=TradeSortDir.asc,
        )
    )
    ids1 = {i.trade_id for i in page1.items}
    ids2 = {i.trade_id for i in page2.items}
    assert ids1.isdisjoint(ids2)  # no overlap across pages
    # Footer aggregates are page-0 only — later pages skip the count/sum scans.
    assert page2.total == 0


@pytest.mark.asyncio
async def test_list_trades_paged_wins_filter_and_total_pnl(database: Database) -> None:
    trade_repo = BacktestTradeRepository(database)
    await trade_repo.save_many(
        [
            _trade("w1", pnl=5.0, hours=0),
            _trade("l1", pnl=-3.0, hours=1),
            _trade("w2", pnl=8.0, hours=2),
        ]
    )
    svc = BacktestStatsService(BacktestRepository(database), trade_repo)

    wins = await svc.list_trades_paged(
        ListTradesQuery(run_id=_RUN, limit=10, filter=TradeFilter.wins)
    )
    assert wins.total == 2
    assert wins.total_pnl == 13.0
    assert all(i.pnl > 0 for i in wins.items)


@pytest.mark.asyncio
async def test_list_markers(database: Database) -> None:
    trade_repo = BacktestTradeRepository(database)
    await trade_repo.save_many([_trade("t1", pnl=1.0, hours=0), _trade("t2", pnl=2.0, hours=1)])
    svc = BacktestStatsService(BacktestRepository(database), trade_repo)

    markers = await svc.list_markers(_RUN)
    assert len(markers) == 2
    assert markers[0].direction == "LONG"
    assert markers[0].entry_time <= markers[1].entry_time


@pytest.mark.asyncio
async def test_get_stats_shape(database: Database) -> None:
    curve = [
        EquityPoint(timestamp=T0, equity=100, drawdown=0.0),
        EquityPoint(timestamp=T0 + timedelta(hours=1), equity=90, drawdown=-0.1),
        EquityPoint(timestamp=T0 + timedelta(hours=2), equity=100, drawdown=0.0),
    ]
    await _seed_run(database, equity_curve=curve)
    trade_repo = BacktestTradeRepository(database)
    await trade_repo.save_many(
        [
            _trade("w1", pnl=10.0, direction="LONG", hours=0),
            _trade("l1", pnl=-4.0, direction="SHORT", hours=1),
            _trade("w2", pnl=6.0, direction="LONG", hours=2),
        ]
    )
    svc = BacktestStatsService(BacktestRepository(database), trade_repo)

    stats = await svc.get_stats(_RUN)
    assert len(stats.pnl_histogram) > 0
    assert len(stats.duration_histogram) > 0
    assert stats.streaks.max_win_streak == 1  # w, l, w -> longest win run is 1
    assert stats.profit_factor_by_direction.long is None  # no long losses
    assert len(stats.drawdowns) == 1
    assert stats.drawdowns[0].recovery_time is not None
