"""Characterization of the concrete classes the production DI graph resolves.

Pins provider wiring (including ``BrokerFactory``) so a DI or provider refactor
that silently swaps an implementation fails here.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from pocketquant.app.di.broker_factory import BrokerFactory
from pocketquant.app.market_data.app_services.quote_app_service import QuoteAppService
from pocketquant.app.market_data.app_services.ws_subscription_manager import (
    WsSubscriptionManager,
)
from pocketquant.backtest.backtest_execution_service import BacktestExecutionService
from pocketquant.core.config import Settings
from pocketquant.core.domain.market_data.interfaces import IDataProvider, IRealtimeQuoteProvider
from pocketquant.core.infra.binance.binance_client import BinanceClient
from pocketquant.core.infra.binance.binance_websocket_client import BinanceWebSocketClient
from pocketquant.core.infra.brokers.okx.okx_broker import OKXBroker
from pocketquant.core.infra.brokers.paper.paper_broker import PaperBroker
from pocketquant.core.infra.scheduling.scheduler import JobScheduler
from pocketquant.engine.app_services.order_app_service import OrderAppService
from pocketquant.engine.app_services.position_app_service import PositionAppService
from pocketquant.engine.app_services.strategy_app_service import StrategyAppService
from pocketquant.engine.app_services.strategy_reconcile_service import StrategyReconcileService
from pocketquant.engine.market_data.app_services.bar_app_service import BarAppService
from pocketquant.engine.market_data.sync_service import SyncService
from pocketquant.engine.market_data.tracked_symbols_service import TrackedSymbolService
from pocketquant.engine.orders_positions_service import OrderPositionQueryService
from pocketquant.engine.strategy_command_service import StrategyCommandService
from pocketquant.engine.strategy_query_service import StrategyQueryService

from .app_factory import build_test_container

pytestmark = pytest.mark.asyncio

_SELF_RESOLVING = [
    SyncService,
    BarAppService,
    QuoteAppService,
    WsSubscriptionManager,
    OrderAppService,
    PositionAppService,
    StrategyAppService,
    StrategyReconcileService,
    BacktestExecutionService,
    TrackedSymbolService,
    StrategyCommandService,
    StrategyQueryService,
    OrderPositionQueryService,
    JobScheduler,
]


@pytest_asyncio.fixture
async def container(settings: Settings):
    c = build_test_container(settings)
    try:
        yield c
    finally:
        await c.close()


async def test_market_data_ports_resolve_to_binance(container) -> None:
    assert isinstance(await container.get(IDataProvider), BinanceClient)
    assert isinstance(await container.get(IRealtimeQuoteProvider), BinanceWebSocketClient)


async def test_broker_factory_types_and_creation(container) -> None:
    factory = await container.get(BrokerFactory)
    assert isinstance(factory, BrokerFactory)
    assert factory.get_available_types() == ["paper", "okx"]
    assert isinstance(factory.create("paper", {}), PaperBroker)
    okx = factory.create("okx", {"api_key": "k", "api_secret": "s", "passphrase": "p"})
    assert isinstance(okx, OKXBroker)
    with pytest.raises(ValueError):
        factory.create("x", {})


@pytest.mark.parametrize("cls", _SELF_RESOLVING, ids=lambda c: c.__name__)
async def test_service_resolves_to_its_own_class(container, cls: type) -> None:
    assert isinstance(await container.get(cls), cls)
