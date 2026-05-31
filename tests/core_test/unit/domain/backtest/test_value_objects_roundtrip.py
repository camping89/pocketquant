"""to_mongo / from_mongo roundtrip tests for all post-Phase-1 VOs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pocketquant.core.domain.backtest import (
    BacktestMetrics,
    EquityPoint,
    Fill,
    OpenLot,
    OptimizationResultEntry,
    Order,
    Trade,
)
from pocketquant.core.infrastructure.brokers.events import OrderEvent
from pocketquant.core.domain.order import OrderSide, OrderStatus, OrderType

NOW = datetime(2026, 1, 5, 10, tzinfo=UTC)


def test_fill_roundtrip_standalone() -> None:
    f = Fill(
        fill_id="f1",
        order_id="o1",
        symbol="BTC:BIN",
        side=OrderSide.BUY,
        quantity=0.5,
        price=65000.0,
        commission=0.65,
        slippage=0.5,
        timestamp=NOW,
    )
    assert Fill.from_mongo(f.to_mongo()) == f


def test_fill_roundtrip_embedded_requires_parent_id() -> None:
    f = Fill(
        fill_id="f1",
        order_id="o1",
        symbol="BTC:BIN",
        side=OrderSide.SELL,
        quantity=1.0,
        price=100.0,
        commission=0.1,
        slippage=0.0,
        timestamp=NOW,
    )
    assert Fill.from_mongo(f.to_mongo(embed=True), order_id="o1") == f


def test_fill_from_mongo_raises_without_order_id() -> None:
    with pytest.raises(ValueError, match="order_id"):
        Fill.from_mongo(
            {
                "fill_id": "f1",
                "symbol": "BTC:BIN",
                "side": "buy",
                "quantity": 1.0,
                "price": 1.0,
                "commission": 0.0,
                "slippage": 0.0,
                "timestamp": NOW,
            }
        )


def test_order_event_roundtrip_with_enum_statuses() -> None:
    ev = OrderEvent(
        timestamp=NOW,
        from_status=OrderStatus.SUBMITTED,
        to_status=OrderStatus.FILLED,
        reason="market_fill",
    )
    assert OrderEvent.from_mongo(ev.to_mongo()) == ev


def test_order_event_initial_has_none_from_status() -> None:
    ev = OrderEvent(
        timestamp=NOW, from_status=None, to_status=OrderStatus.SUBMITTED, reason="submit"
    )
    doc = ev.to_mongo()
    assert doc["from_status"] is None
    assert OrderEvent.from_mongo(doc) == ev


def test_order_roundtrip_with_embedded_events_and_fills() -> None:
    fill = Fill(
        fill_id="f1",
        order_id="o1",
        symbol="BTC:BIN",
        side=OrderSide.BUY,
        quantity=0.01,
        price=65000.0,
        commission=0.65,
        slippage=0.5,
        timestamp=NOW,
    )
    events = [
        OrderEvent(
            timestamp=NOW, from_status=None, to_status=OrderStatus.SUBMITTED, reason="submit"
        ),
        OrderEvent(
            timestamp=NOW,
            from_status=OrderStatus.SUBMITTED,
            to_status=OrderStatus.FILLED,
            reason="market_fill",
        ),
    ]
    o = Order(
        order_id="o1",
        run_id="r1",
        strategy_code="s1",
        symbol="BTC:BIN",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=0.01,
        price=None,
        sl_price=64000,
        tp_price=67000,
        status=OrderStatus.FILLED,
        submitted_at=NOW,
        last_updated_at=NOW,
        events=events,
        fills=[fill],
        resulting_trade_id="t1",
    )
    assert Order.from_mongo(o.to_mongo()) == o


def test_trade_roundtrip_flat_entry_exit_prefix() -> None:
    t = Trade(
        trade_id="t1",
        run_id="r1",
        strategy_code="s1",
        symbol="BTC:BIN",
        direction="LONG",
        entry_order_id="o1",
        entry_price=65000.0,
        entry_time=NOW,
        quantity=0.01,
        exit_order_id="o2",
        exit_price=67000.0,
        exit_time=NOW + timedelta(hours=1),
        sl_price=64000,
        tp_price=67000,
        pnl=19.85,
        commission=1.30,
        duration_seconds=3600.0,
    )
    assert Trade.from_mongo(t.to_mongo()) == t


def test_trade_nullable_order_ids_round_trip() -> None:
    """Migrated trades have None entry/exit_order_id — must round-trip cleanly."""
    t = Trade(
        trade_id="t1",
        run_id="r1",
        strategy_code="s1",
        symbol="BTC:BIN",
        direction="LONG",
        entry_order_id=None,
        entry_price=100.0,
        entry_time=NOW,
        quantity=1.0,
        exit_order_id=None,
        exit_price=110.0,
        exit_time=NOW,
        sl_price=None,
        tp_price=None,
        pnl=10.0,
        commission=0.21,
        duration_seconds=3600.0,
    )
    assert Trade.from_mongo(t.to_mongo()) == t


def test_open_lot_roundtrip() -> None:
    ol = OpenLot(
        symbol="BTC:BIN",
        direction="LONG",
        entry_price=65000.0,
        entry_time=NOW,
        quantity=0.01,
        sl_price=64000,
        tp_price=67000,
        entry_order_id="o1",
        entry_commission_portion=0.15,
    )
    assert OpenLot.from_mongo(ol.to_mongo()) == ol


def test_equity_point_roundtrip() -> None:
    p = EquityPoint(timestamp=NOW, equity=10000.0, drawdown=-0.05)
    assert EquityPoint.from_mongo(p.to_mongo()) == p


def test_metrics_roundtrip_with_duration() -> None:
    m = BacktestMetrics(
        total_return=0.15,
        cagr=0.12,
        sharpe_ratio=1.4,
        sortino_ratio=2.1,
        max_drawdown=-0.08,
        win_rate=0.55,
        profit_factor=1.8,
        total_trades=120,
        winning_trades=66,
        losing_trades=54,
        avg_win=80.5,
        avg_loss=-45.2,
        avg_trade_duration=timedelta(seconds=3600),
        total_commission=245.6,
    )
    assert BacktestMetrics.from_mongo(m.to_mongo()) == m


def test_metrics_zero_second_duration_round_trips_not_none() -> None:
    """Boundary case: 0.0 seconds must NOT round-trip to None (S5 fix)."""
    m = BacktestMetrics.empty()
    doc = {**m.to_mongo(), "avg_trade_duration_seconds": 0.0}
    out = BacktestMetrics.from_mongo(doc)
    assert out.avg_trade_duration == timedelta(seconds=0)


def test_metrics_empty_factory() -> None:
    m = BacktestMetrics.empty()
    assert m.total_trades == 0
    assert m.avg_trade_duration is None


def test_optimization_entry_roundtrip() -> None:
    e = OptimizationResultEntry(
        parameters={"lookback": 10, "threshold": 0.02},
        metrics=BacktestMetrics.empty(),
        backtest_id="bt-1",
        rank=1,
    )
    assert OptimizationResultEntry.from_mongo(e.to_mongo()) == e
