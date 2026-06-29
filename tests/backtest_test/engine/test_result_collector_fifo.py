"""Integration tests — BacktestResultCollector with FIFO lot tracking.

Covers: long-only round-trip, short-only round-trip, scale-in/out, partial fills,
flip LONG↔SHORT, open positions at end.

After Phase 4 storage refactor: collector returns ``CollectedResults`` with
``trades`` (closed round-trips) and ``run.open_positions`` (still-open lots)
instead of a unified ``positions`` list of ``PositionRecord``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_OID, uuid5

import pytest

from pocketquant.backtest.engine.result_collector import BacktestResultCollector
from pocketquant.backtest.models.backtest_config import BacktestConfig
from pocketquant.core.common.time.simulation import clear_simulation_time, set_simulation_time
from pocketquant.core.common.uuid import generate_id_str
from pocketquant.core.domain.brokers.value_objects import OrderResult
from pocketquant.core.domain.order import OrderSide, OrderStatus

RUN_ID = generate_id_str()


@pytest.fixture
def config() -> BacktestConfig:
    return BacktestConfig(
        strategy_code="s1",
        symbol="BTCUSDT:OKX",
        interval="5m",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 31),
        initial_capital=10_000.0,
        commission_bps=10.0,  # 0.1%
    )


@pytest.fixture
def collector(config: BacktestConfig) -> BacktestResultCollector:
    return BacktestResultCollector(config, initial_capital=config.initial_capital, run_id=RUN_ID)


@pytest.fixture(autouse=True)
def reset_sim_time():
    yield
    clear_simulation_time()




def _oid(name: str) -> str:
    """Deterministic uuid string for a short test order handle (collector parses UUIDs)."""
    return str(uuid5(NAMESPACE_OID, name))


def _fill(
    side: OrderSide,
    qty: float,
    price: float,
    order_id: str = "o1",
    sl: float | None = None,
    tp: float | None = None,
) -> OrderResult:
    return OrderResult(
        order_id=_oid(order_id),
        broker_order_id="b" + order_id,
        status=OrderStatus.FILLED,
        filled_quantity=qty,
        filled_price=price,
        side=side,
        sl_price=sl,
        tp_price=tp,
    )


async def _feed(collector: BacktestResultCollector, fill: OrderResult, at: datetime) -> None:
    set_simulation_time(at)
    await collector.on_fill(fill)


@pytest.mark.asyncio
async def test_long_round_trip(collector: BacktestResultCollector) -> None:
    t0 = datetime(2024, 1, 5, 10, tzinfo=UTC)
    await _feed(collector, _fill(OrderSide.BUY, 1.0, 100.0, "o1", sl=90, tp=120), t0)
    await _feed(collector, _fill(OrderSide.SELL, 1.0, 110.0, "o2"), t0 + timedelta(hours=1))

    collected = collector.finalize(RUN_ID, t0, t0 + timedelta(hours=2))
    assert len(collected.trades) == 1
    t = collected.trades[0]
    assert t.direction == "LONG"
    assert t.entry_price == 100.0
    assert t.exit_price == 110.0
    assert t.pnl == pytest.approx(10.0)
    # Commission: 100*1*0.001 + 110*1*0.001 = 0.21
    assert t.commission == pytest.approx(0.21)
    # Equity = 10000 + 10 - 0.21 = 10009.79
    assert collected.run.metrics.total_return == pytest.approx((10009.79 - 10000) / 10000)
    assert collected.run.metrics.total_commission == pytest.approx(0.21)
    # Order link assertions: exit order has resulting_trade_id, entry order does not
    orders = {str(o.order_id): o for o in collected.orders}
    assert orders[_oid("o2")].resulting_trade_id == str(t.trade_id)
    assert orders[_oid("o1")].resulting_trade_id is None
    assert t.entry_order_id == _oid("o1")
    assert t.exit_order_id == _oid("o2")


@pytest.mark.asyncio
async def test_short_round_trip(collector: BacktestResultCollector) -> None:
    t0 = datetime(2024, 1, 5, 10, tzinfo=UTC)
    await _feed(collector, _fill(OrderSide.SELL, 1.0, 100.0, "o1"), t0)
    await _feed(collector, _fill(OrderSide.BUY, 1.0, 90.0, "o2"), t0 + timedelta(hours=1))

    collected = collector.finalize(RUN_ID, t0, t0 + timedelta(hours=2))
    assert len(collected.trades) == 1
    t = collected.trades[0]
    assert t.direction == "SHORT"
    assert t.entry_price == 100.0
    assert t.exit_price == 90.0
    assert t.pnl == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_fifo_two_buys_one_sell(collector: BacktestResultCollector) -> None:
    """2 BUYs different prices → 1 SELL closes both, PnL FIFO-based."""
    t0 = datetime(2024, 1, 5, 10, tzinfo=UTC)
    await _feed(collector, _fill(OrderSide.BUY, 1.0, 100.0, "o1"), t0)
    await _feed(collector, _fill(OrderSide.BUY, 1.0, 110.0, "o2"), t0 + timedelta(minutes=5))
    await _feed(collector, _fill(OrderSide.SELL, 2.0, 120.0, "o3"), t0 + timedelta(hours=1))

    collected = collector.finalize(RUN_ID, t0, t0 + timedelta(hours=2))
    assert len(collected.trades) == 2
    # FIFO: first close has entry 100, second has entry 110
    assert collected.trades[0].entry_price == 100.0
    assert collected.trades[0].pnl == pytest.approx(20.0)
    assert collected.trades[1].entry_price == 110.0
    assert collected.trades[1].pnl == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_partial_close_then_full(collector: BacktestResultCollector) -> None:
    """1 BUY qty=10 → 2 SELLs (4+6)."""
    t0 = datetime(2024, 1, 5, 10, tzinfo=UTC)
    await _feed(collector, _fill(OrderSide.BUY, 10.0, 100.0, "o1"), t0)
    await _feed(collector, _fill(OrderSide.SELL, 4.0, 110.0, "o2"), t0 + timedelta(hours=1))
    await _feed(collector, _fill(OrderSide.SELL, 6.0, 120.0, "o3"), t0 + timedelta(hours=2))

    collected = collector.finalize(RUN_ID, t0, t0 + timedelta(hours=3))
    assert len(collected.trades) == 2
    assert collected.trades[0].quantity == pytest.approx(4.0)
    assert collected.trades[0].pnl == pytest.approx(40.0)  # (110-100)*4
    assert collected.trades[1].quantity == pytest.approx(6.0)
    assert collected.trades[1].pnl == pytest.approx(120.0)  # (120-100)*6


@pytest.mark.asyncio
async def test_flip_long_to_short(collector: BacktestResultCollector) -> None:
    """LONG 10 → SELL 15 → close LONG + open SHORT 5."""
    t0 = datetime(2024, 1, 5, 10, tzinfo=UTC)
    await _feed(collector, _fill(OrderSide.BUY, 10.0, 100.0, "o1"), t0)
    await _feed(collector, _fill(OrderSide.SELL, 15.0, 90.0, "o2"), t0 + timedelta(hours=1))

    collected = collector.finalize(RUN_ID, t0, t0 + timedelta(hours=2))
    # 1 closed LONG + 1 open SHORT
    assert len(collected.trades) == 1
    assert collected.trades[0].direction == "LONG"
    assert collected.trades[0].pnl == pytest.approx(-100.0)  # (90-100)*10
    assert len(collected.run.open_positions) == 1
    ol = collected.run.open_positions[0]
    assert ol.direction == "SHORT"
    assert ol.quantity == pytest.approx(5.0)
    assert ol.entry_price == 90.0


@pytest.mark.asyncio
async def test_flip_short_to_long(collector: BacktestResultCollector) -> None:
    t0 = datetime(2024, 1, 5, 10, tzinfo=UTC)
    await _feed(collector, _fill(OrderSide.SELL, 5.0, 100.0, "o1"), t0)
    await _feed(collector, _fill(OrderSide.BUY, 8.0, 90.0, "o2"), t0 + timedelta(hours=1))

    collected = collector.finalize(RUN_ID, t0, t0 + timedelta(hours=2))
    assert len(collected.trades) == 1
    assert collected.trades[0].direction == "SHORT"
    assert collected.trades[0].pnl == pytest.approx(50.0)  # (100-90)*5
    assert len(collected.run.open_positions) == 1
    ol = collected.run.open_positions[0]
    assert ol.direction == "LONG"
    assert ol.quantity == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_open_position_at_end(collector: BacktestResultCollector) -> None:
    """1 BUY with no matching SELL → 1 OpenLot in run.open_positions, 0 trades."""
    t0 = datetime(2024, 1, 5, 10, tzinfo=UTC)
    await _feed(collector, _fill(OrderSide.BUY, 2.0, 100.0, "o1", sl=90, tp=120), t0)
    collected = collector.finalize(RUN_ID, t0, t0 + timedelta(hours=2))
    assert len(collected.trades) == 0
    assert len(collected.run.open_positions) == 1
    ol = collected.run.open_positions[0]
    assert ol.direction == "LONG"
    assert ol.quantity == 2.0
    assert ol.sl_price == 90
    assert ol.tp_price == 120
    assert ol.entry_order_id == _oid("o1")


@pytest.mark.asyncio
async def test_legacy_fill_without_side_long_only_fallback(
    collector: BacktestResultCollector,
) -> None:
    """OrderResult.side=None → fallback to long-only inference (legacy compat)."""
    t0 = datetime(2024, 1, 5, 10, tzinfo=UTC)
    fill_open = OrderResult(
        order_id=_oid("o1"),
        broker_order_id="b1",
        status=OrderStatus.FILLED,
        filled_quantity=1.0,
        filled_price=100.0,
        side=None,
    )
    fill_close = OrderResult(
        order_id=_oid("o2"),
        broker_order_id="b2",
        status=OrderStatus.FILLED,
        filled_quantity=1.0,
        filled_price=110.0,
        side=None,
    )
    await _feed(collector, fill_open, t0)
    await _feed(collector, fill_close, t0 + timedelta(hours=1))

    collected = collector.finalize(RUN_ID, t0, t0 + timedelta(hours=2))
    assert len(collected.trades) == 1
    assert collected.trades[0].direction == "LONG"
    assert collected.trades[0].pnl == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_total_return_no_regression_for_long_only(
    collector: BacktestResultCollector,
) -> None:
    """Verify long-only flow PnL matches the legacy sequential pairing within rounding."""
    t0 = datetime(2024, 1, 5, 10, tzinfo=UTC)
    # 3 round trips
    for i, (entry, exit_) in enumerate([(100.0, 110.0), (110.0, 105.0), (105.0, 115.0)]):
        await _feed(
            collector,
            _fill(OrderSide.BUY, 1.0, entry, f"b{i}"),
            t0 + timedelta(hours=2 * i),
        )
        await _feed(
            collector,
            _fill(OrderSide.SELL, 1.0, exit_, f"s{i}"),
            t0 + timedelta(hours=2 * i + 1),
        )

    collected = collector.finalize(RUN_ID, t0, t0 + timedelta(hours=10))
    # PnL: 10 - 5 + 10 = 15
    total_pnl = sum(t.pnl for t in collected.trades)
    assert total_pnl == pytest.approx(15.0)
    assert collected.run.metrics.total_commission == pytest.approx(0.645)
    assert collected.run.metrics.winning_trades == 2
    assert collected.run.metrics.losing_trades == 1
