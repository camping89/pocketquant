"""PositionAggregate.id representation lock — UUID in RAM, str in Mongo."""

from __future__ import annotations

from uuid import UUID, uuid7

from pocketquant.core.domain.position import PositionAggregate, PositionSide


def _position() -> PositionAggregate:
    return PositionAggregate.open(
        subscription_id="sub-1",
        symbol="BTCUSDT:BINANCE",
        side=PositionSide.LONG,
        entry_price=100.0,
        quantity=1.0,
    )


def test_factory_assigns_uuid_instance() -> None:
    assert isinstance(_position().id, UUID)


def test_to_mongo_id_is_uuid_string() -> None:
    doc = _position().to_mongo()
    assert isinstance(doc["_id"], str)
    UUID(doc["_id"])  # parseable


def test_roundtrip_preserves_id() -> None:
    p = _position()
    restored = PositionAggregate.from_mongo(p.to_mongo())
    assert restored.id == p.id
    assert isinstance(restored.id, UUID)


def test_from_mongo_reads_legacy_str_uuid_doc() -> None:
    legacy_id = str(uuid7())
    doc = _position().to_mongo()
    doc["_id"] = legacy_id
    restored = PositionAggregate.from_mongo(doc)
    assert restored.id == UUID(legacy_id)


def test_lifecycle_events_carry_str_position_id() -> None:
    p = _position()
    p.close(110.0)
    events = p.collect_events()
    assert events
    for event in events:
        position_id = getattr(event, "position_id", None)
        assert isinstance(position_id, str)
        assert UUID(position_id) == p.id
