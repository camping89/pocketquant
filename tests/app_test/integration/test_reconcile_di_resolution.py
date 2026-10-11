"""DI resolution: reconcile service + strategy feature services resolve.

Proves the dependency graph wires cleanly across providers
(Persistence + Execution + Core + AppTradingServiceProvider).
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from pocketquant.app.di import create_container
from pocketquant.core.config import Settings
from pocketquant.engine.app_services.strategy_reconcile_service import (
    StrategyReconcileService,
)
from pocketquant.engine.strategy_command_service import StrategyCommandService
from pocketquant.engine.strategy_query_service import StrategyQueryService

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def container(settings: Settings):
    c = create_container(settings)
    yield c
    await c.close()


async def test_reconcile_service_resolves(container, settings: Settings) -> None:
    svc = await container.get(StrategyReconcileService)
    assert isinstance(svc, StrategyReconcileService)
    assert svc._interval_s == settings.reconcile_interval_seconds


async def test_start_stop_list_handlers_resolve_with_repo_dep(container) -> None:
    cmd_svc = await container.get(StrategyCommandService)
    query_svc = await container.get(StrategyQueryService)

    assert isinstance(cmd_svc, StrategyCommandService)
    assert isinstance(query_svc, StrategyQueryService)
    # Services carry repo deps, not engine/scheduler deps.
    assert hasattr(cmd_svc, "_sub_repo")
    assert not hasattr(cmd_svc, "_strategy_service")
