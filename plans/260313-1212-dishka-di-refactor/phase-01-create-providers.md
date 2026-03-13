# Phase 1: Install Dishka + Create Provider Modules

## Context Links
- [Dishka research report](../reports/researcher-260313-1204-dishka-library.md)
- [Current services.py](../../src/services.py) — frozen dataclass to replace
- [Current handler_registration.py](../../src/handler_registration.py) — manual handler wiring to replace

## Overview
- **Priority**: P1 (foundation for all other phases)
- **Status**: pending
- **Description**: Install dishka, create provider classes organized by domain

## Key Insights
- Dishka auto-resolves constructor deps via `__init__` type hints — no manual wiring needed for most classes
- Generator factories (`async yield`) handle both init and cleanup
- APP scope = singleton for app lifetime; all current services are singletons
- Handlers are APP-scoped too (registered once with Mediator at startup)
- `SyncSymbolHandler` is shared by `BulkSyncHandler` — dishka caches within scope, so both get same instance automatically
- `BacktestRunner`/`GridOptimizer` are created fresh per handler call — stay outside container

## Files to Create

```
src/providers/
    __init__.py
    config_provider.py        — Settings
    persistence_provider.py   — Database, Cache, 7 repositories
    messaging_provider.py     — EventBus, Mediator
    infrastructure_provider.py — JobScheduler, TradingViewProvider, BrokerFactory, RiskCheckHandler, HealthCoordinator
    market_data_provider.py   — BarManager, QuoteService
    trading_provider.py       — OrderManager, PositionTracker, StrategyEngine
    handler_provider.py       — All 28 CQRS handlers + Mediator registration
```

## Implementation Steps

### 1. Install dishka

```bash
uv add "dishka[fastapi]"
```

### 2. Create `src/providers/__init__.py`

```python
"""Dishka DI providers — one per domain slice."""

from src.providers.config_provider import ConfigProvider
from src.providers.handler_provider import HandlerProvider
from src.providers.infrastructure_provider import InfrastructureProvider
from src.providers.market_data_provider import MarketDataProvider
from src.providers.messaging_provider import MessagingProvider
from src.providers.persistence_provider import PersistenceProvider
from src.providers.trading_provider import TradingProvider

__all__ = [
    "ConfigProvider",
    "HandlerProvider",
    "InfrastructureProvider",
    "MarketDataProvider",
    "MessagingProvider",
    "PersistenceProvider",
    "TradingProvider",
]
```

### 3. Create `src/providers/config_provider.py`

```python
"""Settings provider."""

from dishka import Provider, Scope, provide

from src.config import Settings, get_settings


class ConfigProvider(Provider):
    @provide(scope=Scope.APP)
    def get_settings(self) -> Settings:
        return get_settings()
```

### 4. Create `src/providers/persistence_provider.py`

Database and Cache need async init + cleanup via generator factories. Repositories take Database in constructor — dishka auto-resolves.

```python
"""Database, Cache, and repository providers."""

from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from src.config import Settings
from src.persistence.mongodb import Database
from src.persistence.redis import Cache
from src.persistence.repositories.backtest_repository import BacktestRepository
from src.persistence.repositories.ohlcv_repository import OHLCVRepository
from src.persistence.repositories.optimization_repository import OptimizationRepository
from src.persistence.repositories.order_repository import OrderRepository
from src.persistence.repositories.position_repository import PositionRepository
from src.persistence.repositories.symbol_repository import SymbolRepository
from src.persistence.repositories.sync_status_repository import SyncStatusRepository


class PersistenceProvider(Provider):
    @provide(scope=Scope.APP)
    async def get_database(self, settings: Settings) -> AsyncIterator[Database]:
        database = Database()
        await database.connect(settings)
        yield database
        await database.disconnect()

    @provide(scope=Scope.APP)
    async def get_cache(self, settings: Settings) -> AsyncIterator[Cache]:
        cache = Cache()
        await cache.connect(settings)
        yield cache
        await cache.disconnect()

    # Repositories — auto-resolved via Database type hint in __init__
    ohlcv_repository = provide(OHLCVRepository, scope=Scope.APP)
    order_repository = provide(OrderRepository, scope=Scope.APP)
    position_repository = provide(PositionRepository, scope=Scope.APP)
    backtest_repository = provide(BacktestRepository, scope=Scope.APP)
    optimization_repository = provide(OptimizationRepository, scope=Scope.APP)
    symbol_repository = provide(SymbolRepository, scope=Scope.APP)
    sync_status_repository = provide(SyncStatusRepository, scope=Scope.APP)
```

**IMPORTANT**: Check that every repository `__init__` takes `database: Database` as its only param. If any take additional args, add explicit factory methods instead.

### 5. Create `src/providers/messaging_provider.py`

```python
"""EventBus and Mediator providers."""

from dishka import Provider, Scope, provide

from src.common.mediator.mediator import Mediator
from src.common.messaging import EventBus


class MessagingProvider(Provider):
    @provide(scope=Scope.APP)
    def get_event_bus(self) -> EventBus:
        return EventBus(max_history=100)

    @provide(scope=Scope.APP)
    def get_mediator(self) -> Mediator:
        return Mediator()
```

### 6. Create `src/providers/infrastructure_provider.py`

JobScheduler has conditional init (settings.enable_jobs). Handle with explicit factory.

```python
"""Infrastructure service providers."""

from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from src.common.health import HealthCoordinator
from src.config import Settings
from src.features.risk.check_risk.handler import RiskCheckHandler
from src.infrastructure.brokers import BrokerFactory
from src.infrastructure.scheduling.scheduler import JobScheduler
from src.infrastructure.tradingview import TradingViewProvider


class InfrastructureProvider(Provider):
    @provide(scope=Scope.APP)
    def get_job_scheduler(self, settings: Settings) -> AsyncIterator[JobScheduler]:
        scheduler = JobScheduler()
        if settings.enable_jobs:
            scheduler.initialize(settings)
            scheduler.start()
        yield scheduler
        if settings.enable_jobs:
            scheduler.shutdown(wait=True)

    @provide(scope=Scope.APP)
    def get_tv_provider(self, settings: Settings) -> TradingViewProvider:
        return TradingViewProvider(settings=settings)

    broker_factory = provide(BrokerFactory, scope=Scope.APP)
    risk_handler = provide(RiskCheckHandler, scope=Scope.APP)

    @provide(scope=Scope.APP)
    def get_health_coordinator(self) -> HealthCoordinator:
        return HealthCoordinator(timeout=5.0)
```

### 7. Create `src/providers/market_data_provider.py`

```python
"""Market data service providers."""

from dishka import Provider, Scope, provide

from src.application.market_data.bar_manager import BarManager
from src.application.market_data.quote_service import QuoteService
from src.config import Settings
from src.persistence.redis import Cache
from src.persistence.repositories.ohlcv_repository import OHLCVRepository


class MarketDataProvider(Provider):
    @provide(scope=Scope.APP)
    def get_bar_manager(
        self, cache: Cache, ohlcv_repository: OHLCVRepository
    ) -> BarManager:
        return BarManager(cache=cache, ohlcv_repository=ohlcv_repository)

    @provide(scope=Scope.APP)
    def get_quote_service(
        self, settings: Settings, cache: Cache, bar_manager: BarManager
    ) -> QuoteService:
        return QuoteService(settings=settings, cache=cache, bar_manager=bar_manager)
```

### 8. Create `src/providers/trading_provider.py`

OrderManager, PositionTracker, StrategyEngine all need async post-init. Use generator factories.

```python
"""Trading service providers (with async lifecycle)."""

from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from src.application.strategy.strategy_engine import StrategyEngine
from src.application.trading.order_manager import OrderManager
from src.application.trading.position_tracker import PositionTracker
from src.common.messaging import EventBus
from src.config import Settings
from src.features.risk.check_risk.handler import RiskCheckHandler
from src.infrastructure.brokers import BrokerFactory
from src.persistence.repositories.order_repository import OrderRepository
from src.persistence.repositories.position_repository import PositionRepository


class TradingProvider(Provider):
    @provide(scope=Scope.APP)
    async def get_order_manager(
        self, event_bus: EventBus, order_repository: OrderRepository
    ) -> OrderManager:
        manager = OrderManager(event_bus, order_repository)
        await manager.load_pending_orders()
        return manager

    @provide(scope=Scope.APP)
    async def get_position_tracker(
        self, event_bus: EventBus, position_repository: PositionRepository
    ) -> PositionTracker:
        tracker = PositionTracker(event_bus, position_repository)
        await tracker.start()
        return tracker

    @provide(scope=Scope.APP)
    async def get_strategy_engine(
        self,
        event_bus: EventBus,
        broker_factory: BrokerFactory,
        order_manager: OrderManager,
        position_tracker: PositionTracker,
        risk_handler: RiskCheckHandler,
        settings: Settings,
    ) -> AsyncIterator[StrategyEngine]:
        engine = StrategyEngine(
            event_bus=event_bus,
            broker_factory=broker_factory,
            order_manager=order_manager,
            position_tracker=position_tracker,
            risk_handler=risk_handler,
            default_broker_config={
                "initial_balance": settings.paper_initial_balance,
                "slippage_percent": settings.paper_slippage_percent,
                "api_key": settings.okx_api_key,
                "api_secret": settings.okx_api_secret,
                "passphrase": settings.okx_passphrase,
                "demo": settings.okx_demo_mode,
            },
        )
        await engine.start()
        yield engine
        await engine.stop()
```

### 9. Create `src/providers/handler_provider.py`

This is the most complex provider. All 28 handlers need to be constructed and registered with Mediator. Dishka auto-resolves handler constructors, but Mediator registration is a side-effect that must happen at startup.

**Strategy**: Create a `_MediatorRegistration` sentinel type. A factory resolves all handlers, registers them with Mediator, and returns the sentinel. The lifespan requests this type to trigger registration.

**Alternative (simpler)**: Do handler registration in the lifespan after container creation, using `container.get()`. This avoids a sentinel pattern. **Choose this approach.**

```python
"""CQRS handler providers — all 28 handlers as APP-scoped singletons.

Handlers are resolved by dishka and registered with Mediator in the lifespan
(not in this provider). This provider only declares how to construct them.
"""

from dishka import Provider, Scope, provide

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
from src.features.strategy.get_all.handler import GetStrategiesHandler
from src.features.strategy.get_one.handler import GetStrategyHandler
from src.features.strategy.load.handler import LoadStrategyHandler
from src.features.strategy.start.handler import StartStrategyHandler
from src.features.strategy.stop.handler import StopStrategyHandler
from src.features.trading.get_order.handler import GetOrderHandler
from src.features.trading.get_position.handler import GetPositionHandler
from src.features.trading.list_orders.handler import ListOrdersHandler
from src.features.trading.list_positions.handler import ListPositionsHandler


class HandlerProvider(Provider):
    # Market data (13)
    sync_symbol_handler = provide(SyncSymbolHandler, scope=Scope.APP)
    bulk_sync_handler = provide(BulkSyncHandler, scope=Scope.APP)
    get_ohlcv_handler = provide(GetOHLCVHandler, scope=Scope.APP)
    start_quote_feed_handler = provide(StartQuoteFeedHandler, scope=Scope.APP)
    stop_quote_feed_handler = provide(StopQuoteFeedHandler, scope=Scope.APP)
    subscribe_handler = provide(SubscribeHandler, scope=Scope.APP)
    unsubscribe_handler = provide(UnsubscribeHandler, scope=Scope.APP)
    get_latest_quote_handler = provide(GetLatestQuoteHandler, scope=Scope.APP)
    get_all_quotes_handler = provide(GetAllQuotesHandler, scope=Scope.APP)
    get_sync_status_handler = provide(GetSyncStatusHandler, scope=Scope.APP)
    get_symbol_sync_status_handler = provide(GetSymbolSyncStatusHandler, scope=Scope.APP)
    get_quote_service_status_handler = provide(GetQuoteServiceStatusHandler, scope=Scope.APP)
    list_symbols_handler = provide(ListSymbolsHandler, scope=Scope.APP)

    # Trading (4)
    list_orders_handler = provide(ListOrdersHandler, scope=Scope.APP)
    get_order_handler = provide(GetOrderHandler, scope=Scope.APP)
    list_positions_handler = provide(ListPositionsHandler, scope=Scope.APP)
    get_position_handler = provide(GetPositionHandler, scope=Scope.APP)

    # Strategy (5)
    load_strategy_handler = provide(LoadStrategyHandler, scope=Scope.APP)
    start_strategy_handler = provide(StartStrategyHandler, scope=Scope.APP)
    stop_strategy_handler = provide(StopStrategyHandler, scope=Scope.APP)
    get_strategies_handler = provide(GetStrategiesHandler, scope=Scope.APP)
    get_strategy_handler = provide(GetStrategyHandler, scope=Scope.APP)

    # Backtesting (5)
    run_backtest_handler = provide(RunBacktestHandler, scope=Scope.APP)
    run_optimization_handler = provide(RunOptimizationHandler, scope=Scope.APP)
    get_backtest_handler = provide(GetBacktestHandler, scope=Scope.APP)
    get_optimization_handler = provide(GetOptimizationHandler, scope=Scope.APP)
    list_backtests_handler = provide(ListBacktestsHandler, scope=Scope.APP)
```

**CRITICAL CHECK**: Before using `provide(ClassName, scope=...)` shorthand, verify each handler's `__init__` params match types that dishka can resolve. If any handler takes a param with a name that doesn't match the type hint (e.g., `provider: TradingViewProvider` vs just `TradingViewProvider`), dishka resolves by **type**, not name, so it will work.

**KNOWN ISSUE**: `BulkSyncHandler.__init__` takes `sync_handler: SyncSymbolHandler` — dishka resolves by type `SyncSymbolHandler` which is already in the container. Same instance is returned (APP scope caching). This is correct.

### 10. Verify repository constructors

Before implementing, confirm all 7 repositories take `database: Database` as sole constructor arg:

```bash
grep -n "def __init__" src/persistence/repositories/*.py
```

If any take additional params, add explicit factory methods in `PersistenceProvider`.

## Todo List

- [ ] Run `uv add "dishka[fastapi]"`
- [ ] Create `src/providers/__init__.py`
- [ ] Create `src/providers/config_provider.py`
- [ ] Create `src/providers/persistence_provider.py`
- [ ] Create `src/providers/messaging_provider.py`
- [ ] Create `src/providers/infrastructure_provider.py`
- [ ] Create `src/providers/market_data_provider.py`
- [ ] Create `src/providers/trading_provider.py`
- [ ] Create `src/providers/handler_provider.py`
- [ ] Verify all handler `__init__` type hints match container types
- [ ] Run `pyright src/providers/` — zero errors
- [ ] Run `ruff check src/providers/` — zero errors

## Success Criteria

- All 8 provider files created, pass pyright + ruff
- `uv pip list | grep dishka` shows dishka installed
- No changes to existing code yet (providers are additive)

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Handler `__init__` param names don't match type hints | Dishka resolves by type, not name — should work. Verify with pyright |
| `provide(ClassName)` shorthand fails for classes with complex `__init__` | Fall back to explicit `@provide` factory methods |
| Circular dependency between providers | Unlikely given current tier structure; dishka validates at container creation |
