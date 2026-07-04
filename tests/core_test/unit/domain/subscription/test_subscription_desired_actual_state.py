"""Subscription entity — desired_state/actual_state, mongo round-trip, back-compat, errors.

The control-plane contract: ``desired_state`` is what a human/handler wants;
``actual_state`` is the reconcile loop's mirror of RAM truth. Both default
``stopped`` and tolerate legacy docs lacking the keys.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from pocketquant.core.common.uuid import generate_id
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.subscription import Subscription, SubscriptionAlreadyExistsError

NOW = datetime(2026, 1, 5, 10, tzinfo=UTC)


def _sub(**overrides) -> Subscription:
    base: dict[str, Any] = dict(
        id=generate_id(),
        strategy_code="hitnrun2",
        symbol="BTCUSDT:BINANCE",
        interval=Interval.MINUTE_5,
        created_at=NOW,
    )
    base.update(overrides)
    return Subscription(**base)


def test_defaults_are_stopped() -> None:
    sub = _sub()
    assert sub.desired_state == "stopped"
    assert sub.actual_state == "stopped"


def test_to_mongo_writes_both_state_keys() -> None:
    doc = _sub(desired_state="running", actual_state="running").to_mongo()
    assert doc["desired_state"] == "running"
    assert doc["actual_state"] == "running"


def test_from_mongo_legacy_doc_without_keys_defaults_stopped() -> None:
    legacy = {
        "_id": str(generate_id()),
        "strategy_code": "hitnrun2",
        "symbol": "BTCUSDT:BINANCE",
        "interval": Interval.MINUTE_5.value,
        "created_at": NOW,
    }
    restored = Subscription.from_mongo(legacy)
    assert restored.desired_state == "stopped"
    assert restored.actual_state == "stopped"


def test_from_mongo_preserves_running_desired_state() -> None:
    doc = _sub(desired_state="running", actual_state="stopped").to_mongo()
    restored = Subscription.from_mongo(doc)
    assert restored.desired_state == "running"
    assert restored.actual_state == "stopped"


def test_to_from_mongo_roundtrip_stable_with_states() -> None:
    sub = _sub(desired_state="running", actual_state="running")
    assert Subscription.from_mongo(sub.to_mongo()) == sub


def test_replace_state_keeps_id_stable() -> None:
    sub = _sub()
    mutated = replace(sub, desired_state="running")
    assert mutated.id == sub.id
    assert mutated.desired_state == "running"
    assert sub.desired_state == "stopped"  # original untouched (frozen)


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
    assert err.status_code == 409
    for part in ("hitnrun2", "BTCUSDT:BINANCE", "5m"):
        assert part in str(err)
