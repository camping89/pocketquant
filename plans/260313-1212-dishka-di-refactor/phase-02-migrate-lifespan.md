# Phase 2: Migrate Lifespan to Dishka Container

## Context Links
- [Phase 1: Providers](./phase-01-create-providers.md) — must be complete first
- [Current main.py](../../src/main.py) — 174 lines, 21-step imperative init
- [Current main_extensions.py](../../src/main_extensions.py) — startup helpers

## Overview
- **Priority**: P1
- **Status**: pending
- **Description**: Replace the 21-step imperative lifespan with dishka container creation. Reduce main.py lifespan from ~100 lines to ~30.

## Key Insights

1. **Dishka handles lifecycle**: Generator factories in providers handle connect/disconnect, start/stop
2. **`async with container`**: Entering the container context triggers APP-scope lazy creation; exiting triggers cleanup in reverse order
3. **Middleware still needs `app.state.cache`**: Set `app.state.cache` and `app.state.database` after container creation for middleware hot-path
4. **Handler registration**: Must happen after container resolves handlers. Use `container.get()` in lifespan to pull handlers and register with Mediator
5. **`setup_dishka(container, app)`**: Wires dishka middleware for REQUEST scope management in routes
6. **Post-init tasks** (indexes, health checks, background jobs): Run after container is up, before `yield`

## Files to Modify

| File | Change |
|------|--------|
| `src/main.py` | Replace lifespan body with dishka container |
| `src/main_extensions.py` | Update `ensure_all_indexes`, `register_health_checks`, `start_background_jobs` to take individual deps instead of `Services` |

## Files to Create

| File | Purpose |
|------|---------|
| `src/container.py` | Factory function `create_container()` that assembles all providers |

## Implementation Steps

### 1. Create `src/container.py`

```python
"""Dishka container factory."""

from dishka import AsyncContainer, make_async_container

from src.providers import (
    ConfigProvider,
    HandlerProvider,
    InfrastructureProvider,
    MarketDataProvider,
    MessagingProvider,
    PersistenceProvider,
    TradingProvider,
)


def create_container() -> AsyncContainer:
    """Create the dishka DI container with all providers."""
    return make_async_container(
        ConfigProvider(),
        PersistenceProvider(),
        MessagingProvider(),
        InfrastructureProvider(),
        MarketDataProvider(),
        TradingProvider(),
        HandlerProvider(),
    )
```

### 2. Create handler registration helper

Add a function in `src/container.py` (or keep in separate file) that resolves all handlers from the container and registers with Mediator:

```python
from src.common.mediator.handler_registry import HandlerRegistry

# Import all handler types (same list as handler_provider.py)
from src.features.backtesting.get_optimization.handler import GetOptimizationHandler
# ... all 28 handler imports ...


HANDLER_TYPES: list[type] = [
    SyncSymbolHandler,
    BulkSyncHandler,
    GetOHLCVHandler,
    # ... all 28 ...
]


async def register_handlers(container: AsyncContainer) -> None:
    """Resolve all CQRS handlers from container and register with Mediator."""
    from src.common.mediator.mediator import Mediator

    mediator = await container.get(Mediator)
    registry = HandlerRegistry()

    handlers = []
    for handler_type in HANDLER_TYPES:
        handler = await container.get(handler_type)
        handlers.append(handler)

    registry.register_all(mediator, handlers)
```

**ALTERNATIVE** (simpler, fewer imports): Keep the handler type list in `handler_provider.py` as a module-level constant `ALL_HANDLER_TYPES` and import it.

### 3. Rewrite `src/main.py` lifespan

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    logger.info("application_starting", environment=settings.environment)

    from src.container import create_container, register_handlers

    container = create_container()

    try:
        # Enter APP scope — triggers lazy creation of all requested deps
        async with container:
            # Resolve core deps needed for post-init and middleware
            from src.persistence.mongodb import Database
            from src.persistence.redis import Cache

            database = await container.get(Database)
            cache = await container.get(Cache)

            # Middleware hot-path (IdempotencyMiddleware, RateLimitMiddleware)
            app.state.cache = cache
            app.state.database = database

            # Register CQRS handlers with Mediator
            await register_handlers(container)

            # Post-init tasks
            await ensure_all_indexes(container)
            register_health_checks(container, app)
            await start_background_jobs(container)

            # Wire dishka into FastAPI for route injection
            from dishka.integrations.fastapi import setup_dishka
            setup_dishka(container, app)

            logger.info("application_started")
            yield

        # Container.__aexit__ handles cleanup in reverse order:
        # StrategyEngine.stop() → Cache.disconnect() → Database.disconnect() etc.

    except Exception as e:
        handle_startup_failure(e)
```

**NOTE**: `setup_dishka` should be called inside lifespan (after container is ready) OR in `create_app()`. Check dishka docs — if `setup_dishka` needs to run before lifespan, move container creation to `create_app()` and use `dishka_app = setup_dishka(container, app)` pattern.

**IMPORTANT**: Verify dishka's `setup_dishka` API. Some versions want it called once at app creation, not in lifespan. If so:

```python
def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings)

    app = FastAPI(...)
    configure_middleware(app, settings)
    register_routes(app, settings)

    container = create_container()
    setup_dishka(container, app)  # Adds middleware + stores container on app

    return app
```

And the lifespan would use `app.state.dishka_container` or similar.

### 4. Update `src/main_extensions.py`

Change helper functions to take container or individual deps instead of `Services`:

```python
async def ensure_all_indexes(container: AsyncContainer) -> None:
    """Ensure MongoDB indexes for all repositories."""
    from src.persistence.repositories.backtest_repository import BacktestRepository
    # ... other repo imports ...

    repos = [
        await container.get(OHLCVRepository),
        await container.get(OrderRepository),
        await container.get(PositionRepository),
        await container.get(BacktestRepository),
        await container.get(SyncStatusRepository),
        await container.get(SymbolRepository),
        await container.get(OptimizationRepository),
    ]
    await asyncio.gather(*(repo.ensure_indexes() for repo in repos))
    logger.info("database_indexes_ensured")
```

Similar changes for `register_health_checks` and `start_background_jobs`.

**ALTERNATIVE** (less container-aware): Keep these functions taking individual params and resolve in lifespan before calling them. This keeps main_extensions container-agnostic.

### 5. Handle the health check + system/jobs routes

The `/health` and `/system/jobs` routes in `main_extensions.py` currently use `request.app.state.services`. After migration, they should use `FromDishka[]`:

```python
# In register_routes():
@app.get("/health")
@inject
async def health_check(
    health_coordinator: FromDishka[HealthCoordinator],
) -> dict:
    result = await health_coordinator.check_all()
    result["version"] = settings.app_version
    result["environment"] = settings.environment
    return result

@api.get("/system/jobs")
@inject
async def list_jobs(
    job_scheduler: FromDishka[JobScheduler],
) -> list[dict]:
    return job_scheduler.get_jobs()
```

Or use `DishkaRoute` on these routers.

## Todo List

- [ ] Create `src/container.py` with `create_container()`
- [ ] Add `register_handlers()` function
- [ ] Rewrite `src/main.py` lifespan
- [ ] Update `src/main_extensions.py` helper functions
- [ ] Update health/system routes to use dishka injection
- [ ] Verify `setup_dishka` placement (lifespan vs create_app)
- [ ] Run app: `uvicorn src.main:app` — starts without errors
- [ ] Hit `/health` endpoint — returns valid response
- [ ] Run `pyright src/main.py src/container.py` — zero errors

## Success Criteria

- App starts successfully with dishka container
- All startup logs appear (mongodb.connected, redis.connected, handlers_registered, etc.)
- `/health` returns valid response
- Shutdown logs appear in correct reverse order
- Middleware (idempotency, rate limit) still works via `app.state.cache`

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| `setup_dishka` placement wrong | App won't inject in routes | Test both placements; check dishka FastAPI docs |
| Generator cleanup order wrong | Resources leak on shutdown | Dishka guarantees reverse-creation-order cleanup; verify in logs |
| Lazy resolution means some deps aren't created until first request | Startup validation incomplete | Force-resolve critical deps in lifespan with `container.get()` |
| Container scope confusion (APP vs REQUEST) | Wrong lifecycle for middleware deps | Keep middleware using `app.state.cache` (direct reference, not through dishka) |
