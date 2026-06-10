"""End-to-end: declarative control plane survives a restart.

The success metric of SP1: a subscription with desired_state="running" auto-runs
without any manual start call, and stays running across a process restart. We
prove it by composing the real pieces (real SubscriptionRepository on an
ephemeral Mongo, real StrategyAppService with a PaperBroker, real
StrategyReconcileService) and driving _reconcile() directly for determinism — no
live loop, no sleeps.

Restart is simulated by discarding engine A and building a fresh engine B, then
re-running the rehydrate path (load_strategy per sub, instances start stopped)
before reconciling again. Zero ``start_strategy`` calls appear in the test body.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pocketquant.app.di.broker_factory import BrokerFactory
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.concepts.strategy.services import STRATEGY_REGISTRY
from pocketquant.core.concepts.strategy.value_objects import StrategyConfig
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.subscription import Subscription
from pocketquant.core.persistence.mongodb import Database
from pocketquant.core.persistence.repositories.order_repository import OrderRepository
from pocketquant.core.persistence.repositories.position_repository import (
    PositionRepository,
)
from pocketquant.core.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.execution.app_services.order_app_service import OrderAppService
from pocketquant.execution.app_services.position_app_service import PositionAppService
from pocketquant.execution.app_services.strategy_app_service import StrategyAppService
from pocketquant.execution.app_services.strategy_reconcile_service import (
    StrategyReconcileService,
)
from pocketquant.execution.handlers.risk.check_risk.handler import RiskCheckHandler

pytestmark = pytest.mark.integration

STRATEGY_CODE = "hitnrun2"
SYMBOL = "BTCUSDT:BINANCE"


@pytest.fixture
async def db(settings):
    database = Database()
    await database.connect(settings)
    for coll in ("subscriptions", "orders", "positions"):
        await database.get_collection(coll).drop()
    yield database
    await database.disconnect()


async def _build_engine(db: Database) -> StrategyAppService:
    """Construct a real StrategyAppService with a paper broker (offline-safe)."""
    event_bus = EventBus()
    order_svc = OrderAppService(event_bus, OrderRepository(db))
    await order_svc.load_pending_orders()
    position_svc = PositionAppService(event_bus, PositionRepository(db))
    await position_svc.start()
    engine = StrategyAppService(
        event_bus=event_bus,
        broker_factory=BrokerFactory(event_bus),
        order_app_service=order_svc,
        position_app_service=position_svc,
        risk_check_handler=RiskCheckHandler(),
        default_broker_config={"initial_balance": 100_000.0},
    )
    await engine.start()
    return engine


async def _rehydrate(engine: StrategyAppService, sub: Subscription) -> None:
    """Mirror boot rehydrate: load one stopped instance per subscription."""
    strategy_class = STRATEGY_REGISTRY[sub.strategy_code]
    await engine.load_strategy(
        StrategyConfig(
            id=sub.id,
            name=sub.strategy_code,
            symbol=sub.symbol,
            interval=sub.interval.value,
        ),
        strategy_class=strategy_class,
    )


@pytest.mark.asyncio
async def test_running_sub_auto_resumes_across_simulated_restart(db: Database) -> None:
    repo = SubscriptionRepository(db)
    await repo.ensure_indexes()

    sub = Subscription(
        id=Subscription.deterministic_id(STRATEGY_CODE, SYMBOL, Interval.MINUTE_1),
        strategy_code=STRATEGY_CODE,
        symbol=SYMBOL,
        interval=Interval.MINUTE_1,
        created_at=datetime.now(UTC),
        desired_state="running",
        actual_state="stopped",
    )
    await repo.add(sub)

    # --- Engine A: first boot. Instance loaded (stopped); reconcile starts it.
    engine_a = await _build_engine(db)
    await _rehydrate(engine_a, sub)
    assert engine_a.get_strategy(sub.id).is_running is False

    recon_a = StrategyReconcileService(repo, engine_a, interval_s=0.01)
    await recon_a._reconcile()

    assert engine_a.get_strategy(sub.id).is_running is True
    assert (await repo.get(sub.id)).actual_state == "running"
    await engine_a.stop()

    # --- Engine B: simulated restart. Fresh engine, RAM empty, rehydrate stopped.
    engine_b = await _build_engine(db)
    assert engine_b.get_strategy(sub.id) is None  # RAM cleared on restart
    await _rehydrate(engine_b, sub)
    assert engine_b.get_strategy(sub.id).is_running is False

    recon_b = StrategyReconcileService(repo, engine_b, interval_s=0.01)
    await recon_b._reconcile()

    # Auto-resumed with zero manual start_strategy calls in this test.
    assert engine_b.get_strategy(sub.id).is_running is True
    assert (await repo.get(sub.id)).actual_state == "running"
    await engine_b.stop()


@pytest.mark.asyncio
async def test_stop_convergence_stops_running_strategy(db: Database) -> None:
    repo = SubscriptionRepository(db)
    await repo.ensure_indexes()

    sub = Subscription(
        id=Subscription.deterministic_id(STRATEGY_CODE, SYMBOL, Interval.MINUTE_1),
        strategy_code=STRATEGY_CODE,
        symbol=SYMBOL,
        interval=Interval.MINUTE_1,
        created_at=datetime.now(UTC),
        desired_state="running",
        actual_state="stopped",
    )
    await repo.add(sub)

    engine = await _build_engine(db)
    await _rehydrate(engine, sub)
    recon = StrategyReconcileService(repo, engine, interval_s=0.01)
    await recon._reconcile()
    assert engine.get_strategy(sub.id).is_running is True

    # Human stops it → desired flips → reconcile converges actual to stopped.
    await repo.update_desired_state(sub.id, "stopped")
    await recon._reconcile()

    assert engine.get_strategy(sub.id).is_running is False
    assert (await repo.get(sub.id)).actual_state == "stopped"
    await engine.stop()
