"""A subscription picks its broker, and a venue broker is one adapter per process.

Paper pools per contract spec and retires with its last holder; an ``exness``
broker is one account, so every ``exness`` subscription shares one adapter and
one event stream, even across an unload.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.uuid import generate_id
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.strategy.value_objects import StrategyConfig
from pocketquant.core.domain.subscription import Subscription
from pocketquant.core.domain.symbol import LINEAR_SPEC, ContractSpec
from pocketquant.engine.live.strategy_reconcile_app_service import StrategyReconcileAppService
from pocketquant.engine.strategy.strategy_app_service import StrategyAppService

NOW = datetime(2026, 10, 21, tzinfo=UTC)
GOLD = ContractSpec(multiplier=100.0, tick_size=0.01, lot_step=0.01)


def _sub(broker: str = "paper") -> Subscription:
    return Subscription(
        id=generate_id(),
        strategy_code="hitnrun2",
        symbol="XAUUSD:EXNESS",
        interval=Interval.MINUTE_5,
        created_at=NOW,
        broker=broker,
    )


def test_subscription_round_trips_broker() -> None:
    sub = _sub("exness")

    assert Subscription.from_mongo(sub.to_mongo()).broker == "exness"


def test_document_without_broker_reads_paper() -> None:
    doc = _sub().to_mongo()
    del doc["broker"]

    assert Subscription.from_mongo(doc).broker == "paper"


def test_document_with_unknown_broker_fails_the_load() -> None:
    doc = {**_sub().to_mongo(), "broker": "okx"}

    with pytest.raises(ValueError, match="unknown broker 'okx'"):
        Subscription.from_mongo(doc)


@pytest.mark.asyncio
async def test_reconcile_loads_an_exness_subscription_with_the_exness_broker() -> None:
    loaded: list[StrategyConfig] = []

    class _Engine:
        def get_strategy(self, sub_id: str) -> None:
            return None

        async def load_strategy(self, config: StrategyConfig, strategy_class=None) -> str:
            loaded.append(config)
            return config.id

    recon = StrategyReconcileAppService(None, _Engine())  # type: ignore[arg-type]
    await recon._ensure_instances([_sub("exness"), _sub("paper")])

    assert [c.broker for c in loaded] == ["exness", "paper"]


def _engine() -> tuple[StrategyAppService, MagicMock]:
    def build(broker_type: str, config: dict) -> MagicMock:
        broker = MagicMock(fills_async=True)
        broker.subscribe_trades = AsyncMock()
        broker.subscribe_order_updates = AsyncMock()
        return broker

    factory = MagicMock()
    factory.create = MagicMock(side_effect=build)
    engine = StrategyAppService(
        event_bus=EventBus(),
        broker_factory=factory,
        order_app_service=MagicMock(),
        position_app_service=MagicMock(),
        risk_check_handler=MagicMock(),
    )
    return engine, factory


def _config(sid: str, broker: str, spec: ContractSpec) -> StrategyConfig:
    return StrategyConfig(
        id=sid,
        name=sid,
        symbol="XAUUSD:EXNESS",
        interval="5m",
        broker=broker,
        contract_spec=spec,
    )


@pytest.mark.asyncio
async def test_exness_subscriptions_on_different_specs_share_one_adapter() -> None:
    engine, factory = _engine()
    await engine.load_strategy(_config("gold", "exness", GOLD))
    await engine.load_strategy(_config("fx", "exness", LINEAR_SPEC))

    assert factory.create.call_count == 1
    assert engine._brokers["gold"] is engine._brokers["fx"]
    engine._brokers["gold"].subscribe_order_updates.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_paper_subscriptions_on_different_specs_get_their_own_broker() -> None:
    engine, factory = _engine()
    await engine.load_strategy(_config("gold", "paper", GOLD))
    await engine.load_strategy(_config("fx", "paper", LINEAR_SPEC))

    assert factory.create.call_count == 2


@pytest.mark.asyncio
async def test_exness_load_after_the_last_unload_reuses_the_adapter() -> None:
    engine, factory = _engine()
    await engine.load_strategy(_config("first", "exness", GOLD))
    first = engine._brokers["first"]
    await engine.unload_strategy("first")

    await engine.load_strategy(_config("second", "exness", GOLD))

    assert factory.create.call_count == 1
    assert engine._brokers["second"] is first
