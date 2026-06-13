"""Subscription entity to_mongo / from_mongo roundtrip — pure, no Mongo."""

from __future__ import annotations

from datetime import UTC, datetime

from pocketquant.core.common.uuid import generate_id
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.subscription import Subscription, SubscriptionAlreadyExistsError

NOW = datetime(2026, 1, 5, 10, tzinfo=UTC)


def test_to_from_mongo_roundtrip() -> None:
    sub = Subscription(
        id=generate_id(),
        strategy_code="hitnrun2",
        symbol="BTCUSDT:binance",
        interval=Interval.MINUTE_5,
        created_at=NOW,
    )
    doc = sub.to_mongo()
    assert doc["_id"] == str(sub.id)  # boundary: UUID in RAM, str in Mongo
    assert doc["interval"] == Interval.MINUTE_5.value
    restored = Subscription.from_mongo(doc)
    assert restored == sub


def test_already_exists_error_carries_code_and_triple() -> None:
    err = SubscriptionAlreadyExistsError("hitnrun2", "BTCUSDT:BINANCE", "5m")
    assert err.error_code == "SUBSCRIPTION_ALREADY_EXISTS"
    for part in ("hitnrun2", "BTCUSDT:BINANCE", "5m"):
        assert part in str(err)
