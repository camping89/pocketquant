"""Application dependency injection container.

Single source of truth for all service wiring. Handlers registered here
replace per-feature register.py files.
"""

import asyncio
import inspect
from collections.abc import AsyncIterator
from typing import Any

from dependency_injector import containers, providers

from src.application.market_data.bar_manager import BarManager
from src.application.market_data.quote_service import QuoteService
from src.application.strategy.strategy_engine import StrategyEngine
from src.application.trading.order_manager import OrderManager
from src.application.trading.position_tracker import PositionTracker
from src.common.health import HealthCoordinator
from src.common.mediator.handler_registry import HandlerRegistry
from src.common.mediator.mediator import Mediator
from src.common.messaging import EventBus
from src.config import Settings, get_settings
from src.features.backtesting.get_optimization.handler import GetOptimizationHandler
from src.features.backtesting.get_result.handler import GetBacktestHandler
from src.features.backtesting.list_results.handler import ListBacktestsHandler
from src.features.backtesting.optimize.handler import RunOptimizationHandler
from src.features.backtesting.run.handler import RunBacktestHandler
from src.features.market_data.list_symbols.handler import ListSymbolsHandler
from src.features.market_data.ohlcv.get_ohlcv.handler import GetOHLCVHandler
from src.features.market_data.quotes.get_all.handler import GetAllQuotesHandler
from src.features.market_data.quotes.get_latest.handler import GetLatestQuoteHandler
from src.features.market_data.quotes.start_feed.handler import StartQuoteFeedHandler
from src.features.market_data.quotes.stop_feed.handler import StopQuoteFeedHandler
from src.features.market_data.quotes.subscribe.handler import SubscribeHandler
from src.features.market_data.quotes.unsubscribe.handler import UnsubscribeHandler
from src.features.market_data.status.get_quote_service_status.handler import (
    GetQuoteServiceStatusHandler,
)
from src.features.market_data.status.get_symbol_sync_status.handler import (
    GetSymbolSyncStatusHandler,
)
from src.features.market_data.status.get_sync_status.handler import GetSyncStatusHandler
from src.features.market_data.sync.sync_bulk.handler import BulkSyncHandler
from src.features.market_data.sync.sync_one.handler import SyncSymbolHandler
from src.features.risk.check_risk.handler import RiskCheckHandler
from src.features.strategy.get_all.handler import GetStrategiesHandler
from src.features.strategy.get_one.handler import GetStrategyHandler
from src.features.strategy.load.handler import LoadStrategyHandler
from src.features.strategy.start.handler import StartStrategyHandler
from src.features.strategy.stop.handler import StopStrategyHandler
from src.features.trading.get_order.handler import GetOrderHandler
from src.features.trading.get_position.handler import GetPositionHandler
from src.features.trading.list_orders.handler import ListOrdersHandler
from src.features.trading.list_positions.handler import ListPositionsHandler
from src.infrastructure.brokers import BrokerFactory
from src.infrastructure.scheduling.scheduler import JobScheduler
from src.infrastructure.tradingview import TradingViewProvider
from src.persistence.mongodb import Database
from src.persistence.redis import Cache
from src.persistence.repositories.backtest_repository import BacktestRepository
from src.persistence.repositories.ohlcv_repository import OHLCVRepository
from src.persistence.repositories.optimization_repository import OptimizationRepository
from src.persistence.repositories.order_repository import OrderRepository
from src.persistence.repositories.position_repository import PositionRepository
from src.persistence.repositories.symbol_repository import SymbolRepository
from src.persistence.repositories.sync_status_repository import SyncStatusRepository

# ---------------------------------------------------------------------------
# Async provider resolution helper
# ---------------------------------------------------------------------------


async def resolve(provider: Any) -> Any:
    """Resolve a dependency-injector provider, awaiting if it returns a Future.

    Factory/Singleton providers return Futures in async contexts when they
    depend on async Resource providers.  Uses ``inspect.isawaitable`` —
    the stdlib check that covers coroutines, Futures, and ``__await__``
    objects — so callers don't need ``type: ignore[misc]`` everywhere.
    """
    result = provider()
    if inspect.isawaitable(result):
        return await result
    return result


# ---------------------------------------------------------------------------
# Resource provider init/shutdown generators
# ---------------------------------------------------------------------------


async def init_database(settings: Settings) -> AsyncIterator[Database]:
    """Resource provider: connect on init, disconnect on shutdown."""
    db = Database()
    await db.connect(settings)
    yield db
    await db.disconnect()


async def init_cache(settings: Settings) -> AsyncIterator[Cache]:
    """Resource provider: connect on init, disconnect on shutdown."""
    cache = Cache()
    await cache.connect(settings)
    yield cache
    await cache.disconnect()


async def init_job_scheduler(settings: Settings) -> AsyncIterator[JobScheduler]:
    """Resource provider: initialize and start scheduler, shutdown on teardown."""
    scheduler = JobScheduler()
    if settings.enable_jobs:
        scheduler.initialize(settings)
        scheduler.start()
    yield scheduler
    if settings.enable_jobs:
        scheduler.shutdown(wait=True)


async def init_order_manager(
    event_bus: EventBus, order_repository: OrderRepository
) -> AsyncIterator[OrderManager]:
    """Resource provider: create and load pending orders."""
    om = OrderManager(event_bus, order_repository)
    await om.load_pending_orders()
    yield om


async def init_position_tracker(
    event_bus: EventBus, position_repository: PositionRepository
) -> AsyncIterator[PositionTracker]:
    """Resource provider: create and start position tracking."""
    pt = PositionTracker(event_bus, position_repository)
    await pt.start()
    yield pt


async def init_strategy_engine(
    event_bus: EventBus,
    broker_factory: BrokerFactory,
    order_manager: OrderManager,
    position_tracker: PositionTracker,
    risk_handler: RiskCheckHandler,
    default_broker_config: dict,
) -> AsyncIterator[StrategyEngine]:
    """Resource provider: create, start, and stop strategy engine."""
    engine = StrategyEngine(
        event_bus=event_bus,
        broker_factory=broker_factory,
        order_manager=order_manager,
        position_tracker=position_tracker,
        risk_handler=risk_handler,
        default_broker_config=default_broker_config,
    )
    await engine.start()
    yield engine
    await engine.stop()


def _build_broker_config(settings: Settings) -> dict:
    """Build default broker config from settings."""
    return {
        "initial_balance": settings.paper_initial_balance,
        "slippage_percent": settings.paper_slippage_percent,
        "api_key": settings.okx_api_key,
        "api_secret": settings.okx_api_secret,
        "passphrase": settings.okx_passphrase,
        "demo": settings.okx_demo_mode,
    }


# ---------------------------------------------------------------------------
# Container
# ---------------------------------------------------------------------------


class AppContainer(containers.DeclarativeContainer):
    """IoC container for the PocketQuant application."""

    # Configuration
    settings = providers.Singleton(get_settings)

    # Persistence — async Resource providers
    database = providers.Resource(init_database, settings=settings)
    cache = providers.Resource(init_cache, settings=settings)

    # Repositories
    order_repository = providers.Singleton(OrderRepository, database=database)
    position_repository = providers.Singleton(PositionRepository, database=database)
    backtest_repository = providers.Singleton(BacktestRepository, database=database)
    ohlcv_repository = providers.Singleton(OHLCVRepository, database=database)
    symbol_repository = providers.Singleton(SymbolRepository, database=database)
    sync_status_repository = providers.Singleton(SyncStatusRepository, database=database)
    optimization_repository = providers.Singleton(OptimizationRepository, database=database)

    # Core messaging
    event_bus = providers.Singleton(EventBus, max_history=100)
    mediator = providers.Singleton(Mediator)

    # Infrastructure
    job_scheduler = providers.Resource(init_job_scheduler, settings=settings)
    tv_provider = providers.Singleton(TradingViewProvider, settings=settings)
    broker_factory = providers.Singleton(BrokerFactory)
    risk_handler = providers.Singleton(RiskCheckHandler)
    health_coordinator = providers.Singleton(HealthCoordinator, timeout=5.0)
    default_broker_config = providers.Factory(_build_broker_config, settings=settings)

    # Market data services
    bar_manager = providers.Singleton(BarManager, cache=cache, ohlcv_repository=ohlcv_repository)
    quote_service = providers.Singleton(
        QuoteService, settings=settings, cache=cache, bar_manager=bar_manager
    )

    # Application services — async Resource providers
    order_manager = providers.Resource(
        init_order_manager, event_bus=event_bus, order_repository=order_repository
    )
    position_tracker = providers.Resource(
        init_position_tracker, event_bus=event_bus, position_repository=position_repository
    )
    strategy_engine = providers.Resource(
        init_strategy_engine,
        event_bus=event_bus,
        broker_factory=broker_factory,
        order_manager=order_manager,
        position_tracker=position_tracker,
        risk_handler=risk_handler,
        default_broker_config=default_broker_config,
    )

    # --- CQRS Handlers (Factory = transient, new instance per resolution) ---

    # Market data handlers
    sync_symbol_handler = providers.Factory(
        SyncSymbolHandler,
        provider=tv_provider,
        event_bus=event_bus,
        cache=cache,
        ohlcv_repository=ohlcv_repository,
        symbol_repository=symbol_repository,
        sync_status_repository=sync_status_repository,
    )
    bulk_sync_handler = providers.Factory(BulkSyncHandler, sync_handler=sync_symbol_handler)
    get_ohlcv_handler = providers.Factory(
        GetOHLCVHandler, cache=cache, ohlcv_repository=ohlcv_repository
    )
    start_quote_feed_handler = providers.Factory(StartQuoteFeedHandler, quote_service=quote_service)
    stop_quote_feed_handler = providers.Factory(StopQuoteFeedHandler, quote_service=quote_service)
    subscribe_handler = providers.Factory(SubscribeHandler, quote_service=quote_service)
    unsubscribe_handler = providers.Factory(
        UnsubscribeHandler, quote_service=quote_service, cache=cache
    )
    get_latest_quote_handler = providers.Factory(GetLatestQuoteHandler, cache=cache)
    get_all_quotes_handler = providers.Factory(
        GetAllQuotesHandler, quote_service=quote_service, cache=cache
    )
    get_sync_status_handler = providers.Factory(
        GetSyncStatusHandler, sync_status_repository=sync_status_repository
    )
    get_symbol_sync_status_handler = providers.Factory(
        GetSymbolSyncStatusHandler, sync_status_repository=sync_status_repository
    )
    get_quote_service_status_handler = providers.Factory(
        GetQuoteServiceStatusHandler, quote_service=quote_service
    )
    list_symbols_handler = providers.Factory(
        ListSymbolsHandler, symbol_repository=symbol_repository
    )

    # Trading handlers
    list_orders_handler = providers.Factory(ListOrdersHandler, order_manager=order_manager)
    get_order_handler = providers.Factory(GetOrderHandler, order_manager=order_manager)
    list_positions_handler = providers.Factory(
        ListPositionsHandler, position_tracker=position_tracker
    )
    get_position_handler = providers.Factory(GetPositionHandler, position_tracker=position_tracker)

    # Strategy handlers (handlers use `engine` param name)
    load_strategy_handler = providers.Factory(LoadStrategyHandler, engine=strategy_engine)
    start_strategy_handler = providers.Factory(StartStrategyHandler, engine=strategy_engine)
    stop_strategy_handler = providers.Factory(StopStrategyHandler, engine=strategy_engine)
    get_strategies_handler = providers.Factory(GetStrategiesHandler, engine=strategy_engine)
    get_strategy_handler = providers.Factory(GetStrategyHandler, engine=strategy_engine)

    # Backtesting handlers
    run_backtest_handler = providers.Factory(
        RunBacktestHandler,
        event_bus=event_bus,
        strategy_engine=strategy_engine,
        backtest_repository=backtest_repository,
        ohlcv_repository=ohlcv_repository,
    )
    run_optimization_handler = providers.Factory(
        RunOptimizationHandler,
        event_bus=event_bus,
        strategy_engine=strategy_engine,
        backtest_repository=backtest_repository,
        ohlcv_repository=ohlcv_repository,
        optimization_repository=optimization_repository,
    )
    get_backtest_handler = providers.Factory(
        GetBacktestHandler, backtest_repository=backtest_repository
    )
    get_optimization_handler = providers.Factory(
        GetOptimizationHandler, optimization_repository=optimization_repository
    )
    list_backtests_handler = providers.Factory(
        ListBacktestsHandler, backtest_repository=backtest_repository
    )


# ---------------------------------------------------------------------------
# Handler registration — replaces per-feature register.py files
# ---------------------------------------------------------------------------

# All handler provider attribute names for iteration
_HANDLER_PROVIDERS = [
    # Market data
    "sync_symbol_handler",
    "bulk_sync_handler",
    "get_ohlcv_handler",
    "start_quote_feed_handler",
    "stop_quote_feed_handler",
    "subscribe_handler",
    "unsubscribe_handler",
    "get_latest_quote_handler",
    "get_all_quotes_handler",
    "get_sync_status_handler",
    "get_symbol_sync_status_handler",
    "get_quote_service_status_handler",
    "list_symbols_handler",
    # Trading
    "list_orders_handler",
    "get_order_handler",
    "list_positions_handler",
    "get_position_handler",
    # Strategy
    "load_strategy_handler",
    "start_strategy_handler",
    "stop_strategy_handler",
    "get_strategies_handler",
    "get_strategy_handler",
    # Backtesting
    "run_backtest_handler",
    "run_optimization_handler",
    "get_backtest_handler",
    "get_optimization_handler",
    "list_backtests_handler",
]


async def register_all_handlers(container: AppContainer) -> None:
    """Register all CQRS handlers with mediator from container.

    Replaces all per-feature register.py files.
    Factory providers return Futures when dependencies include async Resources,
    so each resolution must be awaited.
    """
    mediator = container.mediator()
    registry = HandlerRegistry()

    handlers = await asyncio.gather(
        *(resolve(getattr(container, name)) for name in _HANDLER_PROVIDERS)
    )
    registry.register_all(mediator, list(handlers))
