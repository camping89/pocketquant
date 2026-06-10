"""bff is a stateless gateway: it serves reads + writes desired-state, and its
DI graph cannot construct any runtime component.

Two guarantees that make killing/restarting bff safe for live trading:

1. The bff container resolves repos + read/write handlers, but raises on every
   runtime type — JobScheduler, StrategyAppService, StrategyReconcileService,
   BacktestRequestWorker. bff physically cannot start the engine.
2. A POST start over the bff ASGI app only flips ``desired_state`` in Mongo (the
   declarative boundary); no engine is touched. A GET read reflects seeded data.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from dishka.exceptions import NoFactoryError
from httpx import ASGITransport, AsyncClient
from pocketquant.backtest.workers.backtest_request_worker import BacktestRequestWorker
from pocketquant.bff.di.container import create_bff_container
from pocketquant.core.config import Settings
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.subscription import Subscription
from pocketquant.core.persistence.mongodb import Database
from pocketquant.core.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.core.scheduling.scheduler import JobScheduler
from pocketquant.execution.app_services.strategy_app_service import StrategyAppService
from pocketquant.execution.app_services.strategy_reconcile_service import (
    StrategyReconcileService,
)

from tests.bff_test.bff_app_factory import make_bff_test_app

pytestmark = pytest.mark.asyncio

_STRATEGY = "hitnrun2"
_SYMBOL = "BTCUSDT:BINANCE"

# Every runtime component bff must be incapable of building.
_RUNTIME_TYPES = [
    JobScheduler,
    StrategyAppService,
    StrategyReconcileService,
    BacktestRequestWorker,
]


@pytest_asyncio.fixture
async def bff_client(settings: Settings) -> AsyncIterator[AsyncClient]:
    app = make_bff_test_app(settings)
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest.mark.parametrize("runtime_type", _RUNTIME_TYPES, ids=lambda t: t.__name__)
async def test_bff_container_cannot_resolve_runtime(settings: Settings, runtime_type) -> None:
    container = create_bff_container()
    try:
        with pytest.raises(NoFactoryError):
            await container.get(runtime_type)
    finally:
        await container.close()


async def test_bff_start_writes_desired_state_only(
    bff_client: AsyncClient, settings: Settings
) -> None:
    db = Database()
    await db.connect(settings)
    try:
        await db.get_collection("subscriptions").drop()
        repo = SubscriptionRepository(db)
        await repo.ensure_indexes()

        sub = Subscription(
            id=Subscription.deterministic_id(_STRATEGY, _SYMBOL, Interval.MINUTE_1),
            strategy_code=_STRATEGY,
            symbol=_SYMBOL,
            interval=Interval.MINUTE_1,
            created_at=datetime.now(UTC),
            desired_state="stopped",
            actual_state="stopped",
        )
        await repo.add(sub)

        resp = await bff_client.post(f"{settings.api_prefix}/subscriptions/{sub.id}/start")
        assert resp.status_code == 200

        # Declarative boundary: only desired_state flipped. actual_state stays
        # stopped because bff runs no reconcile loop — the headless app would.
        stored = await repo.get(sub.id)
        assert stored is not None
        assert stored.desired_state == "running"
        assert stored.actual_state == "stopped"
    finally:
        await db.get_collection("subscriptions").drop()
        await db.disconnect()


async def test_bff_serves_seeded_read(bff_client: AsyncClient, settings: Settings) -> None:
    db = Database()
    await db.connect(settings)
    try:
        await db.get_collection("subscriptions").drop()
        repo = SubscriptionRepository(db)
        await repo.ensure_indexes()
        sub = Subscription(
            id=Subscription.deterministic_id(_STRATEGY, _SYMBOL, Interval.MINUTE_1),
            strategy_code=_STRATEGY,
            symbol=_SYMBOL,
            interval=Interval.MINUTE_1,
            created_at=datetime.now(UTC),
        )
        await repo.add(sub)

        resp = await bff_client.get(
            f"{settings.api_prefix}/subscriptions/", params={"strategy_code": _STRATEGY}
        )
        assert resp.status_code == 200
        ids = [row["id"] for row in resp.json()]
        assert sub.id in ids
    finally:
        await db.get_collection("subscriptions").drop()
        await db.disconnect()
