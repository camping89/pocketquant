"""Subscription entity to_mongo / from_mongo roundtrip — pure, no Mongo."""

from __future__ import annotations

from datetime import UTC, datetime

from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.subscription import Subscription, SubscriptionAlreadyExistsError

NOW = datetime(2026, 1, 5, 10, tzinfo=UTC)


def test_to_from_mongo_roundtrip() -> None:
    sub = Subscription(
        id=Subscription.deterministic_id("hitnrun2", "BTCUSDT:binance", Interval.MINUTE_5),
        strategy_code="hitnrun2",
        symbol="BTCUSDT:binance",
        interval=Interval.MINUTE_5,
        created_at=NOW,
    )
    doc = sub.to_mongo()
    assert doc["_id"] == sub.id
    assert doc["interval"] == Interval.MINUTE_5.value
    restored = Subscription.from_mongo(doc)
    assert restored == sub


def test_already_exists_error_carries_code() -> None:
    err = SubscriptionAlreadyExistsError("abc123")
    assert err.error_code == "SUBSCRIPTION_ALREADY_EXISTS"
    assert "abc123" in str(err)
