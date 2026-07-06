"""End-to-end: live trade closures flow broker → bus → LiveTradeCollector → trades.

Proves the two live-only wiring points added in R8:
  1. ``StrategyAppService._get_or_create_broker`` subscribes ``_forward_trade_to_bus``
     on each newly-created broker (live path), so a broker closure reaches the bus.
  2. ``LiveTradeCollector`` persists each ``TradeClosedEvent`` as a Trade keyed by
     ``run_id`` = subscription_id.

Backtest is unaffected: it injects its own broker via ``inject_prepared_strategy``
and wires the report collector directly, never touching ``_get_or_create_broker``
or the bus — so a backtest trade is never double-counted here.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.uuid import generate_id
from pocketquant.core.domain.position import TradeClosedEvent
from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY
from pocketquant.core.domain.strategy.value_objects import StrategyConfig
from pocketquant.core.infra.brokers.broker_factory import BrokerFactory
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.order_repository import OrderRepository
from pocketquant.core.infra.persistence.repositories.position_repository import (
    PositionRepository,
)
from pocketquant.core.infra.persistence.repositories.trade_repository import TradeRepository
from pocketquant.engine.execution.order_app_service import OrderAppService
from pocketquant.engine.execution.position_app_service import PositionAppService
from pocketquant.engine.execution.risk_check import RiskCheckHandler
from pocketquant.engine.live.live_trade_collector import LiveTradeCollector
from pocketquant.engine.strategy.strategy_app_service import StrategyAppService

pytestmark = pytest.mark.integration

STRATEGY_CODE = "hitnrun2"
SYMBOL = "BTCUSDT:BINANCE"


@pytest.fixture
async def db(settings):
    database = Database()
    await database.connect(settings)
    for coll in ("orders", "positions", "trades"):
        await database.get_collection(coll).drop()
    yield database
    await database.disconnect()


def _closed_event(subscription_id: str, *, pnl: float, commission: float) -> TradeClosedEvent:
    now = datetime.now(UTC)
    return TradeClosedEvent(
        position_id="p1",
        subscription_id=subscription_id,
        symbol=SYMBOL,
        direction="LONG",
        entry_order_id="o-entry",
        entry_price=100.0,
        entry_time=now,
        quantity=1.0,
        exit_order_id="o-exit",
        exit_price=100.0 + pnl,
        exit_time=now,
        pnl=pnl,
        commission=commission,
        duration_seconds=60.0,
    )


async def _build_engine(bus: EventBus, db: Database) -> StrategyAppService:
    """Real StrategyAppService with a paper broker (offline-safe)."""
    order_svc = OrderAppService(bus, OrderRepository(db))
    await order_svc.load_pending_orders()
    position_svc = PositionAppService(bus, PositionRepository(db))
    await position_svc.start()
    engine = StrategyAppService(
        event_bus=bus,
        broker_factory=BrokerFactory(bus),
        order_app_service=order_svc,
        position_app_service=position_svc,
        risk_check_handler=RiskCheckHandler(),
        default_broker_config={"initial_balance": 100_000.0},
    )
    await engine.start()
    return engine


@pytest.mark.asyncio
async def test_broker_closure_flows_through_bus_to_trades(db: Database) -> None:
    bus = EventBus()
    repo = TradeRepository(db)
    engine = await _build_engine(bus, db)
    collector = LiveTradeCollector(bus, repo, engine)
    await collector.start()

    sub_id = str(generate_id())
    await engine.load_strategy(
        StrategyConfig(id=sub_id, name=STRATEGY_CODE, symbol=SYMBOL, interval="1m"),
        strategy_class=STRATEGY_REGISTRY[STRATEGY_CODE],
    )

    # _get_or_create_broker wired the forward on the created broker; simulate the
    # broker emitting a round-trip closure (what a real fill triggers internally).
    broker = engine._brokers[sub_id]
    assert isinstance(broker, PaperBrokerAdapter)
    assert engine._forward_trade_to_bus in broker._trade_callbacks  # live-only wiring
    await broker._notify_trade_callbacks(_closed_event(sub_id, pnl=12.0, commission=0.3))

    trades = await repo.list_by_subscription(sub_id)
    assert len(trades) == 1
    t = trades[0]
    assert t.run_id == sub_id
    assert t.strategy_code == STRATEGY_CODE
    assert t.pnl == 12.0
    assert t.commission == 0.3


@pytest.mark.asyncio
async def test_two_subs_share_broker_with_single_forward(db: Database) -> None:
    """N subscriptions on one broker → exactly one forward; attribution per event."""
    bus = EventBus()
    repo = TradeRepository(db)
    engine = await _build_engine(bus, db)
    collector = LiveTradeCollector(bus, repo, engine)
    await collector.start()

    sub_a, sub_b = str(generate_id()), str(generate_id())
    for sid in (sub_a, sub_b):
        await engine.load_strategy(
            StrategyConfig(id=sid, name=STRATEGY_CODE, symbol=SYMBOL, interval="1m"),
            strategy_class=STRATEGY_REGISTRY[STRATEGY_CODE],
        )

    broker = engine._brokers[sub_a]
    assert engine._brokers[sub_b] is broker  # reuse loop → one shared broker
    assert isinstance(broker, PaperBrokerAdapter)
    # Wired once on creation, not once per subscription — no double-publish.
    assert broker._trade_callbacks.count(engine._forward_trade_to_bus) == 1

    await broker._notify_trade_callbacks(_closed_event(sub_a, pnl=7.0, commission=0.2))
    await broker._notify_trade_callbacks(_closed_event(sub_b, pnl=-3.0, commission=0.2))

    assert len(await repo.list_by_subscription(sub_a)) == 1
    assert len(await repo.list_by_subscription(sub_b)) == 1


@pytest.mark.asyncio
async def test_collector_persists_event_with_fallback_strategy_code(db: Database) -> None:
    bus = EventBus()
    repo = TradeRepository(db)
    engine = await _build_engine(bus, db)
    collector = LiveTradeCollector(bus, repo, engine)
    await collector.start()

    # No loaded config for this sub → strategy_code falls back to "".
    orphan_sub = str(generate_id())
    await bus.publish(_closed_event(orphan_sub, pnl=-5.0, commission=0.1))

    trades = await repo.list_by_subscription(orphan_sub)
    assert len(trades) == 1
    assert trades[0].strategy_code == ""
    assert trades[0].pnl == -5.0
