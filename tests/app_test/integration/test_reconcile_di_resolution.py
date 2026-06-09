"""DI resolution: reconcile service + rewired start/stop/list handlers resolve.

Proves the Phase-3 dependency swap (start/stop/list_symbols dropped
StrategyAppService for SubscriptionRepository) and the Phase-4 reconcile provider
wire cleanly across providers (Persistence + Execution + Core).
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from dishka import make_async_container
from pocketquant.app.di import (
    ExecutionProvider,
    HandlerProvider,
    InfrastructureProvider,
    MarketDataProvider,
    PersistenceProvider,
)
from pocketquant.core.config import Settings
from pocketquant.execution.app_services.strategy_reconcile_service import (
    StrategyReconcileService,
)
from pocketquant.trading.handlers.strategy.list_symbols.handler import ListSymbolsHandler
from pocketquant.trading.handlers.strategy.start.handler import StartStrategyHandler
from pocketquant.trading.handlers.strategy.stop.handler import StopStrategyHandler

from .app_factory import TestCoreProvider

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def container(settings: Settings):
    c = make_async_container(
        TestCoreProvider(settings),
        PersistenceProvider(),
        InfrastructureProvider(),
        ExecutionProvider(),
        MarketDataProvider(),
        HandlerProvider(),
    )
    yield c
    await c.close()


async def test_reconcile_service_resolves(container, settings: Settings) -> None:
    svc = await container.get(StrategyReconcileService)
    assert isinstance(svc, StrategyReconcileService)
    assert svc._interval_s == settings.reconcile_interval_seconds


async def test_start_stop_list_handlers_resolve_with_repo_dep(container) -> None:
    start = await container.get(StartStrategyHandler)
    stop = await container.get(StopStrategyHandler)
    listing = await container.get(ListSymbolsHandler)

    assert isinstance(start, StartStrategyHandler)
    assert isinstance(stop, StopStrategyHandler)
    assert isinstance(listing, ListSymbolsHandler)
    # Dep swap landed: start/stop carry a sub_repo, not a strategy service.
    assert hasattr(start, "_sub_repo")
    assert hasattr(stop, "_sub_repo")
    assert not hasattr(listing, "_strategy_service")
