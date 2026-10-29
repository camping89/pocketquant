# An exness broker is one account, so every exness subscription shares one adapter and one
# event stream, even across an unload. Paper pools per contract spec and retires with its
# last holder.

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.uuid import generate_id
from pocketquant.core.domain.risk import RiskConfig
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.strategy.value_objects import StrategyConfig
from pocketquant.core.domain.subscription import Subscription
from pocketquant.core.domain.symbol import LINEAR_SPEC, ContractSpec
from pocketquant.engine.backtest.backtest_sandbox_app_service import (
    Continuous24x7CalendarFactory,
    NoClosedTrades,
    NoStoredBars,
)
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


class _RecordingEngine:
    def __init__(self) -> None:
        self.loaded: list[StrategyConfig] = []

    def get_strategy(self, sub_id: str) -> None:
        return None

    async def load_strategy(self, config: StrategyConfig, strategy_class=None) -> str:
        self.loaded.append(config)
        return config.id


@pytest.mark.asyncio
async def test_reconcile_loads_an_exness_subscription_with_the_exness_broker() -> None:
    engine = _RecordingEngine()
    recon = StrategyReconcileAppService(None, engine)  # type: ignore[arg-type]
    await recon._ensure_instances([_sub("exness"), _sub("paper")])

    assert [c.broker for c in engine.loaded] == ["exness", "paper"]


@pytest.mark.asyncio
async def test_reconcile_gives_exness_subscriptions_the_exness_risk() -> None:
    engine = _RecordingEngine()
    exness_risk = RiskConfig(leverage=1000, risk_per_trade=0.10)
    recon = StrategyReconcileAppService(
        None,  # type: ignore[arg-type]
        engine,  # type: ignore[arg-type]
        exness_risk=exness_risk,
    )
    await recon._ensure_instances([_sub("exness"), _sub("paper")])

    exness, paper = engine.loaded
    assert (exness.risk.leverage, exness.risk.risk_per_trade) == (1000, 0.10)
    assert paper.risk == RiskConfig()


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
        bar_repository=NoStoredBars(),  # type: ignore[arg-type]
        calendar_factory=Continuous24x7CalendarFactory(),  # type: ignore[arg-type]
        trade_repository=NoClosedTrades(),  # type: ignore[arg-type]
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
