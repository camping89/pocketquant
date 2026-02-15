# Phase 3: Register Infrastructure + Domain Services

## Context Links

- [Plan overview](./plan.md)
- [Phase 2](./phase-02-persistence-layer-di.md)
- [StrategyEngine](../../src/application/strategy/strategy_engine.py)
- [OrderManager](../../src/application/trading/order_manager.py)
- [PositionTracker](../../src/application/trading/position_tracker.py)
- [JobScheduler](../../src/infrastructure/scheduling/scheduler.py)
- [BrokerFactory](../../src/infrastructure/brokers/factory.py)
- [TradingViewProvider](../../src/infrastructure/tradingview/provider.py)
- [RiskCheckHandler](../../src/features/risk/check_risk/handler.py)
- [EventBus](../../src/common/messaging/event_bus.py)
- [Mediator](../../src/common/mediator/mediator.py)
- [HealthCoordinator](../../src/common/health/coordinator.py)
- [Current manual wiring](../../src/main_extensions.py) (lines 66-124)

## Overview

- **Priority:** P1
- **Status:** pending
- **Effort:** 2h
- **Description:** Register all infrastructure and application services in the container. Convert JobScheduler from static class-method singleton to instance-based. Wire StrategyEngine, OrderManager, PositionTracker as Resource providers with async init/shutdown.

## Key Insights

- `EventBus` and `Mediator` already instance-based -- just need Singleton providers
- `JobScheduler` is the last static class-method singleton -- must convert like Database/Cache
- `StrategyEngine` constructor takes 6 params: event_bus, broker_factory, order_manager, position_tracker, risk_handler, default_broker_config
- `OrderManager` needs `load_pending_orders()` called at startup -- Resource provider
- `PositionTracker` needs `start()` called at startup -- Resource provider
- `StrategyEngine` needs `start()` at startup, `stop()` at shutdown -- Resource provider
- `BrokerFactory` is stateless, simple Singleton
- `TradingViewProvider` takes `settings` -- Singleton
- `RiskCheckHandler` is stateless -- Singleton
- `HealthCoordinator` created in `register_routes()` -- move to container as Singleton
- `default_broker_config` dict currently built in `main_extensions.py` -- derive from Settings in container
- `sync_jobs.py` uses module-level `_mediator` global -- will get Mediator from container instead
<!-- Updated: Validation Session 1 - @event_handler auto-discovery context -->
- `EventBus` has `@event_handler` decorated subscriber methods -- auto-discovery implementation deferred to Phase 4 but EventBus Singleton provider here must support `subscribe()` for it

## Requirements

### Functional
- All services created and wired by container
- Async init/shutdown for Resource providers called in correct order
- `default_broker_config` derived from Settings provider

### Non-Functional
- No behavioral changes
- Service initialization order preserved (DB -> Cache -> repos -> services -> engine)

## Architecture

### JobScheduler: Class-Method -> Instance-Based

```python
# src/infrastructure/scheduling/scheduler.py (AFTER)
class JobScheduler:
    def __init__(self) -> None:
        self._scheduler: AsyncIOScheduler | None = None

    def initialize(self, settings: Settings) -> None:
        # Same logic, using self instead of cls
        ...

    def start(self) -> None:
        self._scheduler.start()

    def shutdown(self, wait: bool = True) -> None:
        if self._scheduler:
            self._scheduler.shutdown(wait=wait)
            self._scheduler = None

    def add_interval_job(self, ...) -> str:
        ...
    # etc.
```

### Resource Providers for Async Services

```python
# In src/container.py

async def init_job_scheduler(settings: Settings) -> AsyncIterator[JobScheduler]:
    scheduler = JobScheduler()
    if settings.enable_jobs:
        scheduler.initialize(settings)
        scheduler.start()
    yield scheduler
    if settings.enable_jobs:
        scheduler.shutdown(wait=True)

async def init_order_manager(event_bus: EventBus) -> AsyncIterator[OrderManager]:
    om = OrderManager(event_bus)
    await om.load_pending_orders()
    yield om

async def init_position_tracker(event_bus: EventBus) -> AsyncIterator[PositionTracker]:
    pt = PositionTracker(event_bus)
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
```

### Container Additions

```python
class AppContainer(containers.DeclarativeContainer):
    # Phase 1
    settings = providers.Singleton(get_settings)

    # Phase 2
    database = providers.Resource(init_database, settings=settings)
    cache = providers.Resource(init_cache, settings=settings)
    # ... repositories ...

    # Phase 3 - Core
    event_bus = providers.Singleton(EventBus, max_history=100)
    mediator = providers.Singleton(Mediator)

    # Phase 3 - Infrastructure
    job_scheduler = providers.Resource(
        init_job_scheduler, settings=settings
    )
    tv_provider = providers.Singleton(TradingViewProvider, settings=settings)
    broker_factory = providers.Singleton(BrokerFactory)
    risk_handler = providers.Singleton(RiskCheckHandler)
    health_coordinator = providers.Singleton(
        HealthCoordinator, timeout=5.0
    )

    # Phase 3 - Application (Resource = async lifecycle)
    order_manager = providers.Resource(
        init_order_manager, event_bus=event_bus
    )
    position_tracker = providers.Resource(
        init_position_tracker, event_bus=event_bus
    )

    # <!-- Red Team: Missing BarManager/QuoteService — 2026-02-15 -->
    bar_manager = providers.Singleton(BarManager, cache=cache)
    quote_service = providers.Singleton(QuoteService, cache=cache)

    # default_broker_config derived via factory
    default_broker_config = providers.Factory(
        _build_broker_config, settings=settings
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
```

### Helper for broker config

```python
def _build_broker_config(settings: Settings) -> dict:
    return {
        "initial_balance": settings.paper_initial_balance,
        "slippage_percent": settings.paper_slippage_percent,
        "api_key": settings.okx_api_key,
        "api_secret": settings.okx_api_secret,
        "passphrase": settings.okx_passphrase,
        "demo": settings.okx_demo_mode,
    }
```

## Related Code Files

| File | Action | Notes |
|------|--------|-------|
| `src/container.py` | modify | Add all service providers |
| `src/infrastructure/scheduling/scheduler.py` | modify | Convert to instance-based |
| `src/common/jobs/__init__.py` | modify | Update re-export |
| `src/application/market_data/sync_jobs.py` | modify | Receive mediator/scheduler via DI, remove global `_mediator` |
| `src/main_extensions.py` | modify | Remove `init_trading_subsystem()` body (services now from container) |

### Files that do NOT change yet (deferred to Phase 4/5)

- Handler files (Phase 4)
- Route files (Phase 5)
- `main.py` lifespan (Phase 5)

## Implementation Steps

1. **Convert `JobScheduler` to instance-based**:
   - Move `_scheduler` from class var to `__init__`
   - Remove all `@classmethod` decorators, `cls` -> `self`
   - Update `src/common/jobs/__init__.py` re-export

2. **Add Resource init functions to container module**:
   - `init_job_scheduler()` -- async generator
   - `init_order_manager()` -- async generator
   - `init_position_tracker()` -- async generator
   - `init_strategy_engine()` -- async generator
   - `_build_broker_config()` -- plain function

3. **Register all providers in AppContainer**:
   - EventBus: `Singleton(EventBus, max_history=100)`
   - Mediator: `Singleton(Mediator)`
   - JobScheduler: `Resource(init_job_scheduler, ...)`
   - TradingViewProvider: `Singleton(TradingViewProvider, settings=settings)`
   - BrokerFactory: `Singleton(BrokerFactory)`
   - RiskCheckHandler: `Singleton(RiskCheckHandler)`
   - HealthCoordinator: `Singleton(HealthCoordinator, timeout=5.0)`
   - OrderManager: `Resource(init_order_manager, ...)`
   - PositionTracker: `Resource(init_position_tracker, ...)`
   - StrategyEngine: `Resource(init_strategy_engine, ...)`

4. **Update `sync_jobs.py`**:
   - Remove module-level `_mediator` global and `set_mediator()` function
   - `register_sync_jobs()` takes `mediator` and `job_scheduler` params
   - Use `job_scheduler.add_interval_job(...)` instead of `JobScheduler.add_interval_job(...)`
   - Sync functions receive mediator as parameter (via partial or closure)

<!-- Red Team: Resource init order unverified — 2026-02-15 -->
5. **SPIKE: Verify Resource provider init order**:
   - Create minimal test: 3 async Resource providers with dependencies (A → B → C)
   - Call `container.init_resources()`, verify init sequence via logging
   - If library doesn't guarantee dependency order: use explicit sequential init in lifespan
   - Document findings

<!-- Red Team: sync_jobs caller update — 2026-02-15 -->
6. **Update `main_extensions.py` IMMEDIATELY (not deferred to Phase 5)**:
   - `start_background_jobs()` takes `job_scheduler` and `mediator` from container
   - `init_trading_subsystem()` simplified -- just calls container init (or removed entirely in Phase 5)
   - Update `set_mediator()` caller in same step as removing the function

6. **Run lint and type check on modified files**

7. **Run test suite**

## Todo List

- [ ] Convert `JobScheduler` from static to instance-based
- [ ] Update `src/common/jobs/__init__.py` re-export
- [ ] Create Resource init functions for async services
- [ ] Create `_build_broker_config` helper
- [ ] Register EventBus, Mediator as Singleton providers
- [ ] Register JobScheduler as Resource provider
- [ ] Register TradingViewProvider, BrokerFactory, RiskCheckHandler as Singletons
- [ ] Register HealthCoordinator as Singleton
- [ ] Register OrderManager, PositionTracker, StrategyEngine as Resource providers
- [ ] Refactor `sync_jobs.py` to receive mediator/scheduler via params
- [ ] Update `main_extensions.py` to use container services
- [ ] Run `ruff check` on all modified files
- [ ] Run `pyright` on all modified files
- [ ] Run full test suite

## Success Criteria

- All services created by container providers
- `container.init_resources()` initializes Database, Cache, JobScheduler, OrderManager, PositionTracker, StrategyEngine in correct order
- `container.shutdown_resources()` shuts down in reverse order
- No module-level mutable globals (`_mediator` removed from sync_jobs.py)
- Background sync jobs register correctly
- All tests pass

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Resource init order matters (DB before repos before services) | High | `dependency-injector` resolves in dependency order automatically |
| sync_jobs.py closure captures stale mediator ref | Medium | Pass explicitly, not via global |
| StrategyEngine.stop() must run before DB disconnect | High | Container shuts down Resources in reverse init order |
| JobScheduler callers elsewhere still use static access | Medium | Update `common/jobs/__init__.py`, backward compat if needed |

## Next Steps

- Phase 4: Wire CQRS handlers as Factory providers, eliminate manual registration
