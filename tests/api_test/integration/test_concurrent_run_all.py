"""Integration test: two simultaneous POST /run-all calls → exactly N jobs, not 2N.

Relies on JobScheduler.add_one_off_job using replace_existing=True so the second
fire overwrites the first rather than creating a duplicate entry.

Requires the scheduler to be running (enable_jobs=True), so this test builds its
own `app_client` using the shared app_factory with an overridden settings fixture.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pocketquant.core.concepts.strategy.value_objects import StrategyConfig
from pocketquant.core.config import Settings
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.infrastructure.scheduling.scheduler import JobScheduler
from pocketquant.infrastructure.persistence.repositories.bar_repository import BarRepository
from pocketquant.execution.app_services.strategy_app_service import StrategyAppService
from pocketquant.infrastructure.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)

from .app_factory import make_test_app

pytestmark = pytest.mark.integration

_API = "/api/v1/strategies"
_STRATEGY_ID = "hitnrun2"
_SYMBOL = "BTC-USDT:BINANCE"
_INTERVAL = "1h"


@pytest.fixture
def _jobs_settings(settings: Settings) -> Settings:
    """Settings with enable_jobs=True so APScheduler initializes."""
    return Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        app_name=settings.app_name,
        app_version=settings.app_version,
        environment=settings.environment,
        mongodb_url=settings.mongodb_url,
        mongodb_database=settings.mongodb_database,
        mongodb_min_pool_size=settings.mongodb_min_pool_size,
        mongodb_max_pool_size=settings.mongodb_max_pool_size,
        redis_url=settings.redis_url,
        redis_cache_ttl=settings.redis_cache_ttl,
        log_level=settings.log_level,
        log_format=settings.log_format,
        enable_jobs=True,
    )


@pytest_asyncio.fixture
async def app_client(_jobs_settings: Settings):  # type: ignore[override]
    """Override base app_client: builds app with scheduler enabled."""
    app = make_test_app(_jobs_settings)
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


def _minimal_bars(n: int = 30) -> list[Bar]:
    base = datetime(2024, 6, 1, tzinfo=UTC)
    price = 50_000.0
    return [
        Bar(
            symbol=_SYMBOL,
            interval=Interval.HOUR_1,
            datetime=base + timedelta(hours=i),
            open=price,
            high=price * 1.001,
            low=price * 0.999,
            close=price,
            volume=5.0,
            tick_count=60,
        )
        for i in range(n)
    ]


@pytest_asyncio.fixture(autouse=True)
async def setup(app_client):
    """Seed bars + load strategy; cleanup after."""
    from pocketquant.core.domain.tracked_symbol.entities import TrackedSymbol
    from pocketquant.infrastructure.persistence.repositories.tracked_symbol_repository import (
        TrackedSymbolRepository,
    )

    container = app_client._transport.app.state.dishka_container  # type: ignore[attr-defined]
    svc: StrategyAppService = await container.get(StrategyAppService)
    bar_repo: BarRepository = await container.get(BarRepository)
    sub_repo: SubscriptionRepository = await container.get(SubscriptionRepository)
    tracked_repo: TrackedSymbolRepository = await container.get(TrackedSymbolRepository)

    # Track the symbol
    await tracked_repo.upsert(TrackedSymbol(symbol=_SYMBOL))

    await bar_repo.insert_many(_minimal_bars(), source="test")

    config = StrategyConfig(
        id=_STRATEGY_ID,
        name="HitNRun2 Concurrent Test",
        symbol=_SYMBOL,
        interval=_INTERVAL,
        broker="paper",
        parameters={
            "entry_lookback_bars": 5,
            "sl_lookback_bars": 10,
            "tp_lookback_bars": 3,
        },
    )
    await svc.unload_strategy(_STRATEGY_ID)
    await svc.load_strategy(config)

    # Clean prior state
    await sub_repo._collection().delete_many({"strategy_code": _STRATEGY_ID})

    yield

    await svc.unload_strategy(_STRATEGY_ID)
    await bar_repo._collection().delete_many({"symbol": _SYMBOL, "interval": _INTERVAL})
    await sub_repo._collection().delete_many({"strategy_code": _STRATEGY_ID})


@pytest.mark.skipif(
    bool(os.getenv("SKIP_SLOW_TESTS")), reason="slow — set SKIP_SLOW_TESTS=1 to skip"
)
@pytest.mark.asyncio
async def test_concurrent_run_all_no_duplicate_jobs(app_client):
    """Two simultaneous run-all calls produce at most N unique jobs per sub, not 2N."""
    container = app_client._transport.app.state.dishka_container  # type: ignore[attr-defined]
    scheduler: JobScheduler = await container.get(JobScheduler)

    # Add a subscription
    add_r = await app_client.post(
        f"{_API}/{_STRATEGY_ID}/subscriptions",
        json={"symbol": _SYMBOL, "interval": _INTERVAL},
    )
    assert add_r.status_code == 201, add_r.text
    sub_id = add_r.json()["id"]
    expected_job_id = f"bt:{sub_id}"

    # Fire two run-all requests concurrently
    r1, r2 = await asyncio.gather(
        app_client.post(f"{_API}/{_STRATEGY_ID}/run-all-backtests"),
        app_client.post(f"{_API}/{_STRATEGY_ID}/run-all-backtests"),
    )
    assert r1.status_code == 202, r1.text
    assert r2.status_code == 202, r2.text

    # Scheduler must have at most 1 job for this subscription (replace_existing=True)
    all_jobs = await scheduler.get_jobs()
    jobs_for_sub = [j for j in all_jobs if j["id"] == expected_job_id]

    assert len(jobs_for_sub) <= 1, (
        f"Expected ≤1 job for {expected_job_id}, got {len(jobs_for_sub)}. "
        f"All job IDs: {[j['id'] for j in all_jobs]}"
    )
