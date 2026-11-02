from __future__ import annotations

from uuid import UUID, uuid7

from pocketquant.core.domain.order import OrderAggregate, OrderSide, OrderType


def _order() -> OrderAggregate:
    return OrderAggregate.create(
        subscription_id="sub-1",
        symbol="BTCUSDT:BINANCE",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1.0,
    )


def test_factory_assigns_uuid_instance() -> None:
    assert isinstance(_order().id, UUID)


def test_to_mongo_id_is_uuid_string() -> None:
    doc = _order().to_mongo()
    assert isinstance(doc["_id"], str)
    UUID(doc["_id"])  # parseable


def test_roundtrip_preserves_id() -> None:
    o = _order()
    restored = OrderAggregate.from_mongo(o.to_mongo())
    assert restored.id == o.id
    assert isinstance(restored.id, UUID)


def test_mongo_round_trip_keeps_sl_and_tp() -> None:
    o = OrderAggregate.create(
        subscription_id="sub-1",
        symbol="BTCUSDT:BINANCE",
        side=OrderSide.BUY,
        order_type=OrderType.STOP_MARKET,
        quantity=1.0,
        stop_price=101.0,
        sl_price=99.0,
        tp_price=103.0,
    )

    restored = OrderAggregate.from_mongo(o.to_mongo())

    assert (restored.sl_price, restored.tp_price) == (99.0, 103.0)


def test_from_mongo_reads_legacy_str_uuid_doc() -> None:
    legacy_id = str(uuid7())
    doc = _order().to_mongo()
    doc["_id"] = legacy_id
    restored = OrderAggregate.from_mongo(doc)
    assert restored.id == UUID(legacy_id)


def test_lifecycle_events_carry_str_order_id() -> None:
    o = _order()
    o.submit("broker-1")
    o.fill(1.0, 100.0)
    events = o.collect_events()
    assert events
    for event in events:
        order_id = getattr(event, "order_id", None)
        assert isinstance(order_id, str)
        assert UUID(order_id) == o.id
