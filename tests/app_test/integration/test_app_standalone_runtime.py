"""App standalone: the headless runtime is fully self-sufficient without bff.

The core SP3 guarantee from the app side — kill/restart bff and live trading is
untouched — rests on the headless app owning the ENTIRE runtime in its own DI
graph: scheduler, strategy engine, reconcile service, backtest worker. No part
of it depends on the bff process existing.

These tests resolve each runtime piece from the real app container (built from
the production providers, wired to ephemeral Mongo/Redis) and drive a reconcile
tick + a worker drain end-to-end. Zero bff involvement anywhere.
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
from pocketquant.backtest.workers.backtest_request_worker import BacktestRequestWorker
from pocketquant.core.common.uuid import generate_id_str
from pocketquant.core.config import Settings
from pocketquant.core.domain.backtest.request import BacktestRequest
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.subscription import Subscription
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.backtest_request_repository import (
    BacktestRequestRepository,
)
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.core.infra.scheduling.scheduler import JobScheduler
from pocketquant.engine.app_services.strategy_app_service import StrategyAppService
from pocketquant.engine.app_services.strategy_reconcile_service import (
    StrategyReconcileService,
)

from .app_factory import TestCoreProvider

pytestmark = pytest.mark.asyncio

_STRATEGY = "hitnrun2"
_SYMBOL = "BTCUSDT:BINANCE"


@pytest_asyncio.fixture
async def app_container(settings: Settings):
    """Full app DI graph — every runtime provider, no bff."""
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
    """The headless runtime — scheduler, engine, reconcile, worker — all resolve
    from the app container with no external process."""
    scheduler = await app_container.get(JobScheduler)
    engine = await app_container.get(StrategyAppService)
    reconcile = await app_container.get(StrategyReconcileService)
    worker = await app_container.get(BacktestRequestWorker)

    assert isinstance(scheduler, JobScheduler)
    assert isinstance(engine, StrategyAppService)
    assert isinstance(reconcile, StrategyReconcileService)
    assert isinstance(worker, BacktestRequestWorker)


async def test_app_reconcile_runs_desired_running_without_bff(
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
        id=Subscription.deterministic_id(_STRATEGY, _SYMBOL, Interval.MINUTE_1),
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
            id=sub.id, name=sub.strategy_code, symbol=sub.symbol, interval=sub.interval.value
        ),
        strategy_class=STRATEGY_REGISTRY[sub.strategy_code],
    )
    assert engine.get_strategy(sub.id).is_running is False

    reconcile = await app_container.get(StrategyReconcileService)
    await reconcile._reconcile()

    assert engine.get_strategy(sub.id).is_running is True
    assert (await repo.get(sub.id)).actual_state == "running"
    await engine.stop()


async def test_app_backtest_worker_drains_queue_without_bff(app_container) -> None:
    """The worker claims and fails a malformed request in-process — the queue is
    drained by the app alone, no bff enqueue path needed for the worker to run."""
    db = await app_container.get(Database)
    await db.get_collection("backtest_requests").drop()

    request_repo = await app_container.get(BacktestRequestRepository)
    worker = await app_container.get(BacktestRequestWorker)

    # A single request with a non-existent strategy: the worker claims it,
    # dispatch raises, and it is marked failed — proving the claim→dispatch→write
    # loop runs end-to-end inside the app graph.
    req = BacktestRequest(
        id=generate_id_str(),
        kind="single",
        status="pending",
        requested_at=datetime.now(UTC),
        strategy_code="does-not-exist",
        config={"strategy_code": "does-not-exist"},
    )
    await request_repo.enqueue(req)

    processed = await worker._drain_once()
    assert processed is True

    done = await request_repo.get(req.id)
    assert done is not None and done.status == "failed"

    await db.get_collection("backtest_requests").drop()
