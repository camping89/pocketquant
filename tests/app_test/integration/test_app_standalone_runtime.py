"""App runtime self-sufficiency: the trading runtime needs no HTTP traffic.

The app owns the ENTIRE runtime in its own DI graph: scheduler, strategy
engine, reconcile service, single-run backtest execution — none of it depends
on any request hitting the API.

These tests resolve each runtime piece from the real app container (built from
the production providers, wired to ephemeral Mongo/Redis) and drive a reconcile
tick + a backtest run end-to-end, without any HTTP client involved.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from dishka import make_async_container

from pocketquant.app.di import (
    BacktestWorkerProvider,
    ExecutionProvider,
    InfrastructureProvider,
    MarketDataProvider,
    PersistenceProvider,
)
from pocketquant.core.common.uuid import generate_id
from pocketquant.core.config import Settings
from pocketquant.core.domain.backtest import BacktestResult
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.subscription import Subscription
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.core.infra.scheduling.scheduler import JobScheduler
from pocketquant.engine.backtest.backtest_execution_service import BacktestExecutionService
from pocketquant.engine.live.strategy_reconcile_app_service import (
    StrategyReconcileAppService,
)
from pocketquant.engine.strategy.strategy_app_service import StrategyAppService

from .app_factory import TestCoreProvider

pytestmark = pytest.mark.asyncio

_STRATEGY = "hitnrun2"
_SYMBOL = "BTCUSDT:BINANCE"


@pytest_asyncio.fixture
async def app_container(settings: Settings):
    """Full app DI graph — every runtime provider."""
    c = make_async_container(
        TestCoreProvider(settings),
        PersistenceProvider(),
        InfrastructureProvider(),
        ExecutionProvider(),
        MarketDataProvider(),
        BacktestWorkerProvider(),
    )
    yield c
    await c.close()


async def test_app_container_resolves_full_runtime(app_container) -> None:
    """The headless runtime — scheduler, engine, reconcile, backtest execution —
    all resolve from the app container with no external process."""
    scheduler = await app_container.get(JobScheduler)
    engine = await app_container.get(StrategyAppService)
    reconcile = await app_container.get(StrategyReconcileAppService)
    execution = await app_container.get(BacktestExecutionService)

    assert isinstance(scheduler, JobScheduler)
    assert isinstance(engine, StrategyAppService)
    assert isinstance(reconcile, StrategyReconcileAppService)
    assert isinstance(execution, BacktestExecutionService)


async def test_app_reconcile_runs_desired_running_without_http(
    app_container, settings: Settings
) -> None:
    """A desired=running subscription converges to actual=running via a single
    reconcile tick driven entirely inside the app graph."""
    db = await app_container.get(Database)
    for coll in ("subscriptions", "orders", "positions"):
        await db.get_collection(coll).drop()

    repo = await app_container.get(SubscriptionRepository)
    await repo.ensure_indexes()

    sub = Subscription(
        id=generate_id(),
        strategy_code=_STRATEGY,
        symbol=_SYMBOL,
        interval=Interval.MINUTE_1,
        created_at=datetime.now(UTC),
        desired_state="running",
        actual_state="stopped",
    )
    await repo.add(sub)

    engine = await app_container.get(StrategyAppService)
    await engine.start()
    # Boot rehydrate: one stopped instance per subscription (mirrors lifespan).
    from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY
    from pocketquant.core.domain.strategy.value_objects import StrategyConfig

    await engine.load_strategy(
        StrategyConfig(
            id=str(sub.id), name=sub.strategy_code, symbol=sub.symbol, interval=sub.interval.value
        ),
        strategy_class=STRATEGY_REGISTRY[sub.strategy_code],
    )
    assert engine.get_strategy(str(sub.id)).is_running is False

    reconcile = await app_container.get(StrategyReconcileAppService)
    await reconcile._reconcile()

    assert engine.get_strategy(str(sub.id)).is_running is True
    assert (await repo.get(str(sub.id))).actual_state == "running"
    await engine.stop()


async def test_app_backtest_execution_runs_without_http(app_container) -> None:
    """A malformed run is executed + marked failed in-process — the engine drains
    via the execution service inside the app graph, no HTTP enqueue path needed."""
    db = await app_container.get(Database)
    await db.get_collection("backtest_runs").drop()

    backtest_repo = await app_container.get(BacktestRepository)
    execution = await app_container.get(BacktestExecutionService)

    # A run for a non-existent strategy: run_single raises before the engine's own
    # guard, execute_and_persist's outer guard flips the doc to failed — proving
    # the run→persist path runs end-to-end inside the app graph.
    run_id = generate_id()
    config = {"strategy_code": "does-not-exist", "symbol": _SYMBOL, "interval": "1m",
              "start_date": "2026-01-01", "end_date": "2026-01-02"}
    await backtest_repo.save(BacktestResult.started(str(run_id), config))

    await execution.execute_and_persist(str(run_id), config)

    done = await backtest_repo.get(str(run_id))
    assert done is not None and done.status == "failed"

    await db.get_collection("backtest_runs").drop()
