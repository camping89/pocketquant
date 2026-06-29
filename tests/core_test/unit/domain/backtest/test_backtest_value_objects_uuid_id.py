"""Backtest VO PK representation lock — UUID in RAM, str in Mongo.

Covers Fill.fill_id, Order.order_id, Trade.trade_id, BacktestResult.id. FK
reference fields (order_id on Fill, run_id, entry/exit_order_id,
resulting_trade_id) stay str — only document PKs flip.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid7

from pocketquant.core.common.uuid import generate_id
from pocketquant.core.domain.backtest import (
    BacktestMetrics,
    BacktestResult,
    Fill,
    Order,
    Trade,
)
from pocketquant.core.domain.order import OrderSide, OrderStatus, OrderType

NOW = datetime(2026, 1, 5, 10, tzinfo=UTC)


def _fill(fill_id: UUID) -> Fill:
    return Fill(
        fill_id=fill_id,
        order_id="o1",
        symbol="BTC:BIN",
        side=OrderSide.BUY,
        quantity=0.5,
        price=65000.0,
        commission=0.65,
        slippage=0.5,
        timestamp=NOW,
    )


def _order(order_id: UUID) -> Order:
    return Order(
        order_id=order_id,
        run_id="r1",
        strategy_code="s1",
        symbol="BTC:BIN",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=0.01,
        price=None,
        sl_price=None,
        tp_price=None,
        status=OrderStatus.FILLED,
        submitted_at=NOW,
        last_updated_at=NOW,
        fills=[_fill(generate_id())],
    )


def _trade(trade_id: UUID) -> Trade:
    return Trade(
        trade_id=trade_id,
        run_id="r1",
        strategy_code="s1",
        symbol="BTC:BIN",
        direction="LONG",
        entry_order_id="o1",
        entry_price=100.0,
        entry_time=NOW,
        quantity=1.0,
        exit_order_id="o2",
        exit_price=110.0,
        exit_time=NOW,
        sl_price=None,
        tp_price=None,
        pnl=10.0,
        commission=0.21,
        duration_seconds=3600.0,
    )


# --- Fill.fill_id ---------------------------------------------------------


def test_fill_to_mongo_writes_str_fill_id() -> None:
    f = _fill(generate_id())
    doc = f.to_mongo()
    assert isinstance(doc["fill_id"], str)
    UUID(doc["fill_id"])


def test_fill_roundtrip_preserves_uuid_fill_id() -> None:
    f = _fill(generate_id())
    restored = Fill.from_mongo(f.to_mongo())
    assert restored.fill_id == f.fill_id
    assert isinstance(restored.fill_id, UUID)
    assert isinstance(restored.order_id, str)  # FK stays str


def test_fill_from_mongo_reads_legacy_str_uuid_doc() -> None:
    legacy = str(uuid7())
    doc = _fill(generate_id()).to_mongo()
    doc["fill_id"] = legacy
    assert Fill.from_mongo(doc).fill_id == UUID(legacy)


# --- Order.order_id -------------------------------------------------------


def test_order_to_mongo_writes_str_id() -> None:
    o = _order(generate_id())
    doc = o.to_mongo()
    assert isinstance(doc["_id"], str)
    UUID(doc["_id"])


def test_order_roundtrip_preserves_uuid_id_and_embedded_fill_fk() -> None:
    o = _order(generate_id())
    restored = Order.from_mongo(o.to_mongo())
    assert restored.order_id == o.order_id
    assert isinstance(restored.order_id, UUID)
    # Embedded fill gets parent _id back as its str FK.
    assert isinstance(restored.fills[0].order_id, str)
    assert UUID(restored.fills[0].order_id) == o.order_id


def test_order_from_mongo_reads_legacy_str_uuid_doc() -> None:
    legacy = str(uuid7())
    doc = _order(generate_id()).to_mongo()
    doc["_id"] = legacy
    assert Order.from_mongo(doc).order_id == UUID(legacy)


# --- Trade.trade_id -------------------------------------------------------


def test_trade_to_mongo_writes_str_id() -> None:
    doc = _trade(generate_id()).to_mongo()
    assert isinstance(doc["_id"], str)
    UUID(doc["_id"])


def test_trade_roundtrip_preserves_uuid_id() -> None:
    t = _trade(generate_id())
    restored = Trade.from_mongo(t.to_mongo())
    assert restored.trade_id == t.trade_id
    assert isinstance(restored.trade_id, UUID)
    assert isinstance(restored.entry_order_id, str)  # FK stays str


def test_trade_from_mongo_reads_legacy_str_uuid_doc() -> None:
    legacy = str(uuid7())
    doc = _trade(generate_id()).to_mongo()
    doc["_id"] = legacy
    assert Trade.from_mongo(doc).trade_id == UUID(legacy)


# --- BacktestResult.id ------------------------------------------------------


def _backtest_result(run_id: UUID) -> BacktestResult:
    return BacktestResult(
        id=run_id,
        strategy_code="s1",
        config_snapshot={},
        metrics=BacktestMetrics.empty(),
        equity_curve=[],
        started_at=NOW,
        completed_at=NOW,
        status="finished",
    )


def test_backtest_result_to_mongo_writes_str_id() -> None:
    doc = _backtest_result(generate_id()).to_mongo()
    assert isinstance(doc["_id"], str)
    UUID(doc["_id"])


def test_backtest_result_roundtrip_preserves_uuid_id() -> None:
    r = _backtest_result(generate_id())
    restored = BacktestResult.from_mongo(r.to_mongo())
    assert restored.id == r.id
    assert isinstance(restored.id, UUID)


def test_backtest_result_from_mongo_reads_legacy_str_uuid_doc() -> None:
    legacy = str(uuid7())
    doc = _backtest_result(generate_id()).to_mongo()
    doc["_id"] = legacy
    assert BacktestResult.from_mongo(doc).id == UUID(legacy)
