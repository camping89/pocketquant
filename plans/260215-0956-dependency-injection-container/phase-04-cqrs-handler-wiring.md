# Phase 4: Wire CQRS Handlers + Eliminate Manual Registration

## Context Links

- [Plan overview](./plan.md)
- [Phase 3](./phase-03-infrastructure-services.md)
- [Mediator](../../src/common/mediator/mediator.py)
- [HandlerRegistry](../../src/common/mediator/handler_registry.py)
- [market_data register.py](../../src/features/market_data/register.py)
- [trading register.py](../../src/features/trading/register.py)
- [strategy register.py](../../src/features/strategy/register.py)
- [backtesting register.py](../../src/features/backtesting/register.py)
- [SyncSymbolHandler example](../../src/features/market_data/sync/sync_one/handler.py)

## Overview

- **Priority:** P1
- **Status:** completed
- **Effort:** 2h
- **Description:** Register all ~27 CQRS handlers as Factory (transient) providers in the container. Delete per-feature `register.py` files — container module owns `register_all_handlers()`. Auto-discover `@event_handler` decorated methods. Wire Mediator to use container-provided handlers.

## Key Insights

- Currently each `register.py` file manually instantiates handlers with their dependencies
- Handlers are constructed once at startup and reused (not truly per-request factories)
<!-- Updated: Validation Session 1 - Handlers changed from Singleton to Factory (transient) -->
- **Decision: Factory providers (transient)** for handlers -- fresh instance per resolution for isolation, prevents accidental state leakage if handlers evolve
- The `@handles` decorator pattern stays -- container auto-discovers and registers handlers with Mediator
<!-- Updated: Validation Session 1 - register.py files removed, registration moved to container module -->
- **Per-feature `register.py` files are DELETED** -- container module owns both handler Factory definitions AND `register_all_handlers()` function
- Container is single source of truth for all handler wiring -- eliminates circular import risk
<!-- Updated: Validation Session 1 - @event_handler auto-discovery added -->
- **`@event_handler` decorated methods auto-discovered** -- container scans handler instances and registers event subscribers with EventBus automatically

### Handler Dependency Map (from register.py files)

**market_data (13 handlers):**
- `SyncSymbolHandler(tv_provider, event_bus)` -- needs TradingViewProvider, EventBus
- `BulkSyncHandler(sync_handler)` -- needs SyncSymbolHandler instance
- `GetOHLCVHandler()` -- no deps (uses static Cache/OHLCVRepository, migrate to DI)
- `StartQuoteFeedHandler(settings)` -- needs Settings
- `StopQuoteFeedHandler(settings)` -- needs Settings
- `SubscribeHandler(settings)` -- needs Settings
- `UnsubscribeHandler(settings)` -- needs Settings
- `GetLatestQuoteHandler()` -- no deps (uses static Cache)
- `GetAllQuotesHandler(settings)` -- needs Settings
- `GetSyncStatusHandler()` -- no deps
- `GetSymbolSyncStatusHandler()` -- no deps
- `GetQuoteServiceStatusHandler(settings)` -- needs Settings
- `ListSymbolsHandler()` -- no deps

**trading (4 handlers):**
- `ListOrdersHandler(order_manager)` -- needs OrderManager
- `GetOrderHandler(order_manager)` -- needs OrderManager
- `ListPositionsHandler(position_tracker)` -- needs PositionTracker
- `GetPositionHandler(position_tracker)` -- needs PositionTracker

**strategy (5 handlers):**
- `LoadStrategyHandler(strategy_engine)` -- needs StrategyEngine
- `StartStrategyHandler(strategy_engine)` -- needs StrategyEngine
- `StopStrategyHandler(strategy_engine)` -- needs StrategyEngine
- `GetStrategiesHandler(strategy_engine)` -- needs StrategyEngine
- `GetStrategyHandler(strategy_engine)` -- needs StrategyEngine

**backtesting (5 handlers):**
- `RunBacktestHandler(event_bus, strategy_engine)` -- needs EventBus, StrategyEngine
- `RunOptimizationHandler(event_bus, strategy_engine)` -- needs EventBus, StrategyEngine
- `GetBacktestHandler()` -- no deps
- `GetOptimizationHandler()` -- no deps
- `ListBacktestsHandler()` -- no deps

## Requirements

### Functional
- All handlers registered in container with correct dependencies as Factory providers
- Mediator populated from `register_all_handlers()` in container module
- Existing `@handles` decorator preserved on handler classes
- `@event_handler` decorated methods auto-discovered and registered with EventBus
- All CQRS dispatch works identically

### Non-Functional
- Per-feature `register.py` files deleted (replaced by container-owned registration)
- Handler files that use `Cache` or repositories directly should receive them via constructor (inject repos/cache)
- No more hidden static dependencies in handler code

## Architecture

<!-- Updated: Validation Session 1 - Changed from Singleton to Factory providers -->
### Container Handler Providers (Factory = Transient)

```python
# In src/container.py (additions)
class AppContainer(containers.DeclarativeContainer):
    ...
    # Market data handlers (Factory = new instance per resolution)
    sync_symbol_handler = providers.Factory(
        SyncSymbolHandler,
        provider=tv_provider,
        event_bus=event_bus,
        cache=cache,
        ohlcv_repository=ohlcv_repository,
        symbol_repository=symbol_repository,
        sync_status_repository=sync_status_repository,
    )
    bulk_sync_handler = providers.Factory(
        BulkSyncHandler,
        sync_handler=sync_symbol_handler,
    )
    get_ohlcv_handler = providers.Factory(
        GetOHLCVHandler,
        cache=cache,
        ohlcv_repository=ohlcv_repository,
    )
    # ... etc for all handlers

    # Trading handlers
    list_orders_handler = providers.Factory(
        ListOrdersHandler, order_manager=order_manager
    )
    # ... etc

    # Strategy handlers
    load_strategy_handler = providers.Factory(
        LoadStrategyHandler, strategy_engine=strategy_engine
    )
    # ... etc

    # Backtesting handlers
    run_backtest_handler = providers.Factory(
        RunBacktestHandler,
        event_bus=event_bus,
        strategy_engine=strategy_engine,
    )
    # ... etc
```

<!-- Updated: Validation Session 1 - register.py files deleted, single registration in container module -->
### Handler Registration (in container module)

```python
# In src/container.py — single registration function replaces all register.py files
def register_all_handlers(container: AppContainer) -> None:
    """Register all CQRS handlers with mediator from container."""
    mediator = container.mediator()
    registry = HandlerRegistry()

    handlers = [
        # Market data
        container.sync_symbol_handler(),
        container.bulk_sync_handler(),
        container.get_ohlcv_handler(),
        container.start_quote_feed_handler(),
        container.stop_quote_feed_handler(),
        container.subscribe_handler(),
        container.unsubscribe_handler(),
        container.get_latest_quote_handler(),
        container.get_all_quotes_handler(),
        container.get_sync_status_handler(),
        container.get_symbol_sync_status_handler(),
        container.get_quote_service_status_handler(),
        container.list_symbols_handler(),
        # Trading
        container.list_orders_handler(),
        container.get_order_handler(),
        container.list_positions_handler(),
        container.get_position_handler(),
        # Strategy
        container.load_strategy_handler(),
        container.start_strategy_handler(),
        container.stop_strategy_handler(),
        container.get_strategies_handler(),
        container.get_strategy_handler(),
        # Backtesting
        container.run_backtest_handler(),
        container.run_optimization_handler(),
        container.get_backtest_handler(),
        container.get_optimization_handler(),
        container.list_backtests_handler(),
    ]

    registry.register_all(mediator, handlers)
```

<!-- Updated: Validation Session 1 - @event_handler auto-discovery -->
### Event Handler Auto-Discovery

```python
# In src/container.py — scan handlers for @event_handler decorated methods
def register_event_handlers(container: AppContainer) -> None:
    """Auto-discover @event_handler decorated methods and register with EventBus."""
    event_bus = container.event_bus()
    # Iterate all handler providers, resolve instance, scan for @event_handler methods
    for provider in _get_handler_providers(container):
        handler_instance = provider()
        for attr_name in dir(handler_instance):
            method = getattr(handler_instance, attr_name, None)
            if callable(method) and hasattr(method, '_event_type'):
                event_bus.subscribe(method._event_type, method)
```

**Decision:** Container module owns all registration. Per-feature `register.py` files are deleted.

### Handler Constructor Updates (inject repos/cache)

Handlers that currently use `Cache` or repositories as static calls need constructor injection:

```python
# BEFORE (src/features/market_data/sync/sync_one/handler.py)
class SyncSymbolHandler(Handler[SyncSymbolCommand, SyncResponse]):
    def __init__(self, provider: TradingViewProvider, event_bus: EventBus):
        self.provider = provider
        self.event_bus = event_bus

    async def handle(self, request):
        # Static calls:
        await SyncStatusRepository.upsert(...)
        await OHLCVRepository.upsert_many(records)
        await Cache.delete_pattern(...)

# AFTER
class SyncSymbolHandler(Handler[SyncSymbolCommand, SyncResponse]):
    def __init__(
        self,
        provider: TradingViewProvider,
        event_bus: EventBus,
        cache: Cache,
        ohlcv_repository: OHLCVRepository,
        symbol_repository: SymbolRepository,
        sync_status_repository: SyncStatusRepository,
    ):
        self.provider = provider
        self.event_bus = event_bus
        self._cache = cache
        self._ohlcv_repo = ohlcv_repository
        self._symbol_repo = symbol_repository
        self._sync_status_repo = sync_status_repository

    async def handle(self, request):
        await self._sync_status_repo.upsert(...)
        await self._ohlcv_repo.upsert_many(records)
        await self._cache.delete_pattern(...)
```

<!-- Updated: Validation Session 1 - register.py files deleted instead of modified -->
## Related Code Files

| File | Action | Notes |
|------|--------|-------|
| `src/container.py` | modify | Add all handler Factory providers + `register_all_handlers()` + `register_event_handlers()` |
| `src/features/market_data/register.py` | **delete** | Registration moved to container module |
| `src/features/trading/register.py` | **delete** | Registration moved to container module |
| `src/features/strategy/register.py` | **delete** | Registration moved to container module |
| `src/features/backtesting/register.py` | **delete** | Registration moved to container module |
| `src/features/market_data/sync/sync_one/handler.py` | modify | Inject Cache, repos via constructor |
| `src/features/market_data/ohlcv/get_ohlcv/handler.py` | modify | Inject Cache, OHLCVRepository |
| `src/features/market_data/quotes/get_latest/handler.py` | modify | Inject Cache |
| `src/features/market_data/quotes/get_all/handler.py` | modify | Inject Cache |
| `src/features/market_data/quotes/unsubscribe/handler.py` | modify | Inject Cache |
| Other handlers with static deps | modify | Inject via constructor |

## Implementation Steps

<!-- Red Team: Handler count audit — 2026-02-15 -->
1. **Audit all handler constructors via grep**:
   - Run `grep -r "@handles" src/features/` to get exact handler count and request types
   - Separate CQRS handlers (@handles decorated) from domain services (RiskCheckHandler is NOT a CQRS handler)
   - List every handler, its current constructor params, and any static calls to Cache/repos inside `handle()` method

<!-- Red Team: Circular import constraint — 2026-02-15 -->
1b. **Add architectural constraint test**:
   - Create `tests/test_container_isolation.py` (like existing `test_domain_purity.py`)
   - AST check: `src/features/**/*.py` and `src/application/**/*.py` must NOT import `src.container`
   - Container imports handlers, never reverse

2. **Update handler constructors to accept injected deps**:
   - For each handler that calls `Cache.xxx()` or `SomeRepository.xxx()` statically:
     - Add the dependency to `__init__`
     - Replace static calls with instance calls
   - Keep `@handles` decorator unchanged

<!-- Updated: Validation Session 1 - Factory providers, register.py deleted, event handler auto-discovery -->
3. **Register handler Factory providers in `src/container.py`**:
   - Add Factory provider for each handler (transient, new instance per resolution)
   - Wire dependencies (repos, cache, services) from existing container providers

4. **Add `register_all_handlers()` to container module**:
   - Single function that resolves all handler instances and registers with Mediator via HandlerRegistry
   - Replaces all per-feature `register.py` files

5. **Add `register_event_handlers()` to container module**:
   - Auto-discover `@event_handler` decorated methods on handler instances
   - Register discovered methods with EventBus

6. **Delete per-feature `register.py` files**:
   - Delete `src/features/market_data/register.py`
   - Delete `src/features/trading/register.py`
   - Delete `src/features/strategy/register.py`
   - Delete `src/features/backtesting/register.py`

7. **Update `main_extensions.py` callers**:
   - Replace `register_handlers(mediator, ...)` calls with `container.register_all_handlers()`
   - Remove manual handler construction

6. **Remove backward-compat `_default_instance` from BaseRepository**:
   - All callers now use instance-based repos via DI
   - Remove the fallback code added in Phase 2

7. **Run lint, type check, tests**

## Todo List

- [ ] Audit all handler constructors and static deps
- [ ] Update `SyncSymbolHandler` constructor (inject cache, 3 repos)
- [ ] Update `GetOHLCVHandler` constructor (inject cache, ohlcv_repo)
- [ ] Update `GetLatestQuoteHandler` constructor (inject cache)
- [ ] Update `GetAllQuotesHandler` constructor (inject cache)
- [ ] Update `UnsubscribeHandler` constructor (inject cache)
- [ ] Update remaining handlers with static deps
- [ ] Register all handler **Factory** providers in container
- [ ] Add `register_all_handlers()` function to container module
- [ ] Add `register_event_handlers()` function to container module
- [ ] Delete `src/features/market_data/register.py`
- [ ] Delete `src/features/trading/register.py`
- [ ] Delete `src/features/strategy/register.py`
- [ ] Delete `src/features/backtesting/register.py`
- [ ] Update `main_extensions.py` to call container registration functions
- [ ] Remove `_default_instance` backward compat from BaseRepository
- [ ] Run `ruff check` on all modified files
- [ ] Run `pyright` on all modified files
- [ ] Run full test suite

## Success Criteria

- All handlers have explicit constructor dependencies (no hidden static calls)
- All handlers registered via container Factory providers (transient)
- Per-feature `register.py` files deleted — `register_all_handlers()` in container module
- `@event_handler` methods auto-discovered and registered with EventBus
- Mediator dispatch works for all request types
- No static Repository or Cache calls remain in handler code
- All tests pass

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Missing a handler's hidden static dep | Medium | Audit with grep for `Cache.` and `Repository.` in handler files |
| Container too large (many providers) | Low | Under 200 LOC with careful formatting; split into helper module if needed |
| Circular import (container imports handlers, handlers import container) | High | Container imports handler classes; handlers never import container |
| BulkSyncHandler depends on SyncSymbolHandler instance | Low | Container resolves in order, Singleton ensures same instance |

## Next Steps

- Phase 5: FastAPI integration, replace `app.state`, refactor lifespan, cleanup
