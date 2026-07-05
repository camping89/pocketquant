"""End-to-end test — BacktestAppService persists to all 3 collections.

Drives a minimal real backtest (synthetic bars + scripted strategy orders)
via the real BacktestAppService against a real Mongo testcontainer and asserts
that backtest_runs / backtest_orders / backtest_trades are populated correctly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Generator
from datetime import UTC, datetime, timedelta

import pytest

from pocketquant.backtest.engine.backtest_app_service import BacktestAppService
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.time.simulation import clear_simulation_time
from pocketquant.core.domain.backtest import BacktestConfig
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.order import OrderAggregate, OrderSide, OrderType
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter
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

_SYM = "BTCUSDT:BINANCE"


@pytest.fixture(autouse=True)
def reset_sim() -> Generator[None]:
    clear_simulation_time()
    yield
    clear_simulation_time()


class _FakeBarRepo:
    def __init__(self, bars: list[Bar]) -> None:
        self._bars = bars

    async def stream(
        self,
        symbol: str,
        interval: Interval,
        start_datetime: datetime | None = None,
        end_datetime: datetime | None = None,
    ) -> AsyncIterator[Bar]:
        for b in self._bars:
            yield b


def _bar(
    idx: int, *, close: float, t0: datetime, low: float | None = None, high: float | None = None
) -> Bar:
    return Bar(
        symbol=_SYM,
        interval=Interval.MINUTE_1,
        datetime=t0 + timedelta(minutes=idx),
        open=close,
        high=high or close + 0.1,
        low=low or close - 0.1,
        close=close,
        volume=1.0,
    )


@pytest.mark.asyncio
async def test_end_to_end_persists_three_collections(database: Database) -> None:
    """Round-trip: 1 entry + 1 exit → 1 trade, 2 orders, slim run in Mongo."""
    bus = EventBus()
    broker = PaperBrokerAdapter(
        initial_balance=100_000, slippage_percent=0, fill_delay_ms=0, event_bus=bus
    )
    await broker.connect()
    backtest_repo = BacktestRepository(database)
    order_repo = BacktestOrderRepository(database)
    trade_repo = BacktestTradeRepository(database)

    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    bars = [_bar(i, close=100.0, t0=t0) for i in range(5)]

    # Strategy: open at bar 1, close at bar 3 — implemented as a bar handler.
    sent_open = False
    sent_close = False

    async def scripted_strategy(event: BarCompletedEvent) -> None:
        nonlocal sent_open, sent_close
        if not sent_open:
            o = OrderAggregate.create(
                subscription_id="scripted",
                symbol=_SYM,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=1.0,
            )
            await broker.submit_order(o)
            sent_open = True
        elif (
            sent_open
            and not sent_close
            and event.bar_start is not None
            and event.bar_start >= t0 + timedelta(minutes=3)
        ):
            o = OrderAggregate.create(
                subscription_id="scripted",
                symbol=_SYM,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=1.0,
            )
            await broker.submit_order(o)
            sent_close = True

    bus.subscribe(BarCompletedEvent, scripted_strategy)

    config = BacktestConfig(
        strategy_code="scripted",
        symbol=_SYM,
        interval="1m",
        start_date=datetime(2026, 1, 1),
        end_date=datetime(2026, 1, 31),
        initial_capital=100_000.0,
        slippage_bps=0.0,
        commission_bps=10.0,
    )

    runner = BacktestAppService(
        event_bus=bus,
        broker=broker,
        backtest_repository=backtest_repo,
        bar_repository=_FakeBarRepo(bars),  # pyright: ignore[reportArgumentType]
        order_repository=order_repo,
        trade_repository=trade_repo,
        persist_results=True,
    )
    result = await runner.run(config)

    # Run doc: slim, no trades/positions arrays.
    run_coll = database.get_collection("backtest_runs")
    doc = await run_coll.find_one({"_id": str(result.id)})
    assert doc is not None
    assert "trades" not in doc
    assert "positions" not in doc
    assert doc["status"] == "finished"

    # Orders: 2 (entry + exit), each FILLED with ≥2 events + ≥1 fill.
    orders = await order_repo.list_by_run(str(result.id))
    assert len(orders) == 2
    for o in orders:
        assert o.status.value == "filled"
        assert len(o.events) >= 2
        assert len(o.fills) >= 1

    # Trades: 1 closed round-trip.
    trades = await trade_repo.list_by_run(str(result.id))
    assert len(trades) == 1
    t = trades[0]
    assert t.direction == "LONG"
    assert t.entry_price == 100.0
    assert t.exit_price == 100.0
    # entry_order_id and exit_order_id link to existing orders.
    order_ids = {str(o.order_id) for o in orders}
    assert t.entry_order_id in order_ids
    assert t.exit_order_id in order_ids
    # Back-link: exit order has resulting_trade_id pointing at this trade.
    exit_order = next(o for o in orders if str(o.order_id) == t.exit_order_id)
    assert exit_order.resulting_trade_id == str(t.trade_id)


@pytest.mark.asyncio
async def test_sl_auto_exit_order_records_sell_side(database: Database) -> None:
    """Regression: synthetic SL exit must persist with side=SELL (closes LONG).

    Previously the on_event handler created a stub with placeholder side=BUY,
    and on_fill saw an existing entry and skipped the side backfill.
    """
    bus = EventBus()
    broker = PaperBrokerAdapter(
        initial_balance=100_000, slippage_percent=0, fill_delay_ms=0, event_bus=bus
    )
    await broker.connect()
    backtest_repo = BacktestRepository(database)
    order_repo = BacktestOrderRepository(database)
    trade_repo = BacktestTradeRepository(database)

    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    # Bar 0: entry at 100 with SL=95.  Bar 1: low=94 → SL triggered → synthetic SELL exit.
    bars = [
        _bar(0, close=100.0, t0=t0),
        _bar(1, close=98.0, t0=t0, low=94.0),
        _bar(2, close=98.0, t0=t0),
    ]
    entered = False

    async def scripted(event: BarCompletedEvent) -> None:
        nonlocal entered
        if not entered:
            o = OrderAggregate.create(
                subscription_id="sl-test",
                symbol=_SYM,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=1.0,
                sl_price=95.0,
            )
            await broker.submit_order(o)
            entered = True

    bus.subscribe(BarCompletedEvent, scripted)

    config = BacktestConfig(
        strategy_code="sl-test",
        symbol=_SYM,
        interval="1m",
        start_date=datetime(2026, 1, 1),
        end_date=datetime(2026, 1, 31),
        initial_capital=100_000.0,
        slippage_bps=0.0,
        commission_bps=0.0,
    )
    runner = BacktestAppService(
        event_bus=bus,
        broker=broker,
        backtest_repository=backtest_repo,
        bar_repository=_FakeBarRepo(bars),  # pyright: ignore[reportArgumentType]
        order_repository=order_repo,
        trade_repository=trade_repo,
        persist_results=True,
    )
    result = await runner.run(config)

    orders = await order_repo.list_by_run(str(result.id))
    assert len(orders) == 2
    sides = sorted([o.side.value for o in orders])
    assert sides == ["buy", "sell"], f"expected one buy + one sell, got {sides}"
    # The SELL is the synthetic exit; must back-link to the trade.
    sell_order = next(o for o in orders if o.side == OrderSide.SELL)
    trades = await trade_repo.list_by_run(str(result.id))
    assert len(trades) == 1
    assert sell_order.resulting_trade_id == str(trades[0].trade_id)
