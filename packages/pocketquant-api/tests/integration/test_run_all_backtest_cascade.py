"""Integration test: run-all backtest → poll until done → cascade delete cleans DB.

Requires the scheduler to be initialized, so this test builds its own
`app_client` with `enable_jobs=True` rather than the default (jobs-disabled)
fixture from conftest.py.

Skippable with env var SKIP_SLOW_TESTS=1 when CI is constrained.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pocketquant.backtest.persistence.backtest_repository import BacktestRepository
from pocketquant.core.concepts.strategy.value_objects import StrategyConfig
from pocketquant.core.config import Settings
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.persistence.repositories.bar_repository import BarRepository
from pocketquant.trading.app_services.strategy_app_service import StrategyAppService

from .app_factory import make_test_app

pytestmark = pytest.mark.integration

_API = "/api/v1/strategies"
_STRATEGY_ID = "hitnrun2"   # must be in STRATEGY_REGISTRY
_SYMBOL = "BTCUSDT:BINANCE"
_INTERVAL = "1h"
_N_BARS = 100
_POLL_TIMEOUT_S = 30
_POLL_INTERVAL_S = 1.0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def _jobs_settings(settings: Settings) -> Settings:
    """Settings copy with enable_jobs=True so APScheduler initializes."""
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


def _synthetic_bars(n: int) -> list[Bar]:
    """Generate n hourly bars with deterministic OHLCV values."""
    base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    bars: list[Bar] = []
    price = 40_000.0
    for i in range(n):
        ts = base + timedelta(hours=i)
        bars.append(
            Bar(
                symbol=_SYMBOL,
                interval=Interval.HOUR_1,
                datetime=ts,
                open=price,
                high=price * 1.002,
                low=price * 0.998,
                close=price * 1.001,
                volume=10.0 + i,
                tick_count=60,
            )
        )
        price *= 1.0005
    return bars


@pytest_asyncio.fixture(autouse=True)
async def setup_strategy_and_bars(app_client):
    """Seed bars + load strategy; cleanup after."""
    from pocketquant.core.domain.tracked_symbol.entities import TrackedSymbol
    from pocketquant.core.persistence.repositories.tracked_symbol_repository import (
        TrackedSymbolRepository,
    )

    container = app_client._transport.app.state.dishka_container  # type: ignore[attr-defined]
    svc: StrategyAppService = await container.get(StrategyAppService)
    bar_repo: BarRepository = await container.get(BarRepository)
    bt_repo: BacktestRepository = await container.get(BacktestRepository)
    tracked_repo: TrackedSymbolRepository = await container.get(TrackedSymbolRepository)

    # Track the symbol
    await tracked_repo.upsert(TrackedSymbol(symbol=_SYMBOL))

    # Seed synthetic bar data
    await bar_repo.insert_many(_synthetic_bars(_N_BARS), source="test")

    config = StrategyConfig(
        id=_STRATEGY_ID,
        name="HitNRun2 Test",
        symbol=_SYMBOL,
        interval=_INTERVAL,
        broker="paper",
        parameters={
            "entry_lookback_bars": 10,
            "sl_lookback_bars": 20,
            "tp_lookback_bars": 5,
        },
    )
    await svc.unload_strategy(_STRATEGY_ID)
    await svc.load_strategy(config)

    from pocketquant.trading.persistence.subscription_repository import (
        SubscriptionRepository,
    )

    # Clean prior test data
    sub_repo: SubscriptionRepository = await container.get(SubscriptionRepository)
    await bt_repo._collection().delete_many({"strategy_code": _STRATEGY_ID})
    await sub_repo._collection().delete_many({"strategy_code": _STRATEGY_ID})

    yield

    await svc.unload_strategy(_STRATEGY_ID)
    await bar_repo._collection().delete_many(
        {"symbol": _SYMBOL, "interval": _INTERVAL}
    )
    await bt_repo.delete_by_strategy_code(_STRATEGY_ID)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(bool(os.getenv("SKIP_SLOW_TESTS")), reason="slow — set SKIP_SLOW_TESTS=1 to skip")
@pytest.mark.asyncio
async def test_run_all_backtest_cascade_delete(app_client):
    """Full flow: add sub → run-all → poll until done → delete strategy → DB clean."""
    from pocketquant.backtest.persistence.backtest_repository import BacktestRepository

    container = app_client._transport.app.state.dishka_container  # type: ignore[attr-defined]
    bt_repo: BacktestRepository = await container.get(BacktestRepository)

    # 1. Add subscription
    add_r = await app_client.post(
        f"{_API}/{_STRATEGY_ID}/subscriptions",
        json={"symbol": _SYMBOL, "interval": _INTERVAL},
    )
    assert add_r.status_code == 201, add_r.text
    sub_id = add_r.json()["id"]

    # 2. Trigger run-all
    run_r = await app_client.post(f"{_API}/{_STRATEGY_ID}/run-all-backtests")
    assert run_r.status_code == 202, run_r.text
    job_ids = run_r.json()["job_ids"]
    assert len(job_ids) == 1

    # 3. Poll until status is 'completed' or 'failed' (max 30s)
    deadline = asyncio.get_event_loop().time() + _POLL_TIMEOUT_S
    status_doc = None
    while asyncio.get_event_loop().time() < deadline:
        status_doc = await bt_repo.get_subscription_status(sub_id)
        if status_doc and status_doc["status"] in ("completed", "failed"):
            break
        await asyncio.sleep(_POLL_INTERVAL_S)

    assert status_doc is not None, "Backtest status doc never created"
    assert status_doc["status"] == "completed", (
        f"Expected 'completed', got '{status_doc['status']}'. "
        f"error_msg={status_doc.get('error_msg')}"
    )

    # 4. GET backtest via API
    bt_r = await app_client.get(f"/api/v1/subscriptions/{sub_id}/backtest")
    assert bt_r.status_code == 200, bt_r.text
    assert bt_r.json()["status"] == "completed"

    # 5. Cascade delete
    del_r = await app_client.delete(f"{_API}/{_STRATEGY_ID}")
    assert del_r.status_code == 204, del_r.text

    # 6. Verify backtest_runs has 0 docs for this strategy
    remaining = await bt_repo.find_by_subscription(sub_id)
    assert remaining is None, "Expected backtest doc deleted after cascade"
