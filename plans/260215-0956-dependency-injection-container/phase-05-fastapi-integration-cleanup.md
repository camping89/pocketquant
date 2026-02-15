# Phase 5: FastAPI Integration + Cleanup

## Context Links

- [Plan overview](./plan.md)
- [Phase 4](./phase-04-cqrs-handler-wiring.md)
- [Current main.py](../../src/main.py)
- [Current main_extensions.py](../../src/main_extensions.py)
- [Mediator dependency](../../src/common/mediator/dependencies.py)
- [Example route](../../src/features/trading/list_orders/route.py)
- [Health checks](../../src/common/health/checks.py)

## Overview

- **Priority:** P1
- **Status:** completed
- **Effort:** 2h
- **Description:** Wire FastAPI `Depends()` helpers to resolve from container. Replace all `app.state` usage with DI injection. Refactor `main.py` lifespan to use `container.init_resources()` / `container.shutdown_resources()`. Remove `main_extensions.py` manual wiring. Final cleanup and validation.

## Key Insights

- Currently `get_mediator()` reads from `request.app.state.mediator` -- replace with container resolution
- `app.state.strategy_engine`, `app.state.order_manager`, `app.state.position_tracker` used only in lifespan shutdown + possibly routes
- `dependency-injector` has native FastAPI integration: `from dependency_injector.wiring import Provide, inject`
- But explicit `Depends()` functions are clearer and follow existing pattern
- `container.init_resources()` calls all Resource providers in dependency order
- `container.shutdown_resources()` shuts down in reverse order -- replaces manual shutdown
- `main_extensions.py` becomes mostly obsolete: `init_trading_subsystem()`, `start_background_jobs()`, `ensure_all_indexes()` all handled by container
- Keep `configure_middleware()` and `register_routes()` as-is (they're app config, not DI)
- `handle_startup_failure()` stays as utility

## Requirements

### Functional
- `Depends()` resolves Mediator, and any other services routes need, from container
- Lifespan uses `container.init_resources()` for startup, `container.shutdown_resources()` for teardown
- Health check uses HealthCoordinator from container
- Background jobs registered after container init
- All `app.state` service locator usage removed

### Non-Functional
- `main.py` stays under 80 LOC
- `main_extensions.py` reduced to middleware + routes helpers only (or deleted)
- No orphan code or dead imports

## Architecture

### Container-Aware Depends() Helpers

```python
# src/common/mediator/dependencies.py (AFTER)
from fastapi import Request
from src.common.mediator.mediator import Mediator


def get_mediator(request: Request) -> Mediator:
    """Get Mediator from DI container."""
    return request.app.state.container.mediator()
```

This minimal change keeps the `Depends(get_mediator)` pattern in all routes unchanged. The only difference: it resolves from `container.mediator()` instead of `app.state.mediator`.

### Lifespan Refactored

```python
# src/main.py (AFTER)
from src.container import AppContainer

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    container: AppContainer = app.state.container
    settings = container.settings()
    logger.info("application_starting", environment=settings.environment)

    try:
        # Initialize all Resource providers (db, cache, scheduler, services)
        await container.init_resources()

        # Post-init: indexes + handler registration + background jobs
        await ensure_all_indexes(container)
        register_all_handlers(container)
        register_background_jobs(container)

    except Exception as e:
        # <!-- Red Team: Init failure rollback — 2026-02-15 -->
        # Cleanup already-initialized resources before exiting
        await container.shutdown_resources()
        handle_startup_failure(e)

    logger.info("application_started")
    yield
    logger.info("application_stopping")

    # <!-- Red Team: Graceful shutdown sequence — 2026-02-15 -->
    # Explicit shutdown order: stop scheduler → drain → then resources
    scheduler = container.job_scheduler()
    settings = container.settings()
    if settings.enable_jobs:
        scheduler.shutdown(wait=True)

    engine = container.strategy_engine()
    await engine.stop()

    # Shutdown all Resources in reverse order (DB/Cache last)
    await container.shutdown_resources()
    logger.info("application_stopped")
```

### ensure_all_indexes from Container

```python
async def ensure_all_indexes(container: AppContainer) -> None:
    """Create MongoDB indexes for all repositories."""
    await container.order_repository().ensure_indexes()
    await container.position_repository().ensure_indexes()
    await container.backtest_repository().ensure_indexes()
    await container.ohlcv_repository().ensure_indexes()
    await container.sync_status_repository().ensure_indexes()
    await container.symbol_repository().ensure_indexes()
    await container.optimization_repository().ensure_indexes()
    logger.info("database_indexes_ensured")
```

<!-- Updated: Validation Session 1 - register.py files deleted, registration in container module -->
### register_all_handlers from Container

```python
# Already defined in src/container.py (Phase 4)
# Called directly: register_all_handlers(container)
# No per-feature register.py files — all deleted in Phase 4
from src.container import register_all_handlers, register_event_handlers
```

### register_background_jobs from Container

```python
def register_background_jobs(container: AppContainer) -> None:
    settings = container.settings()
    if settings.enable_jobs:
        from src.application.market_data.sync_jobs import register_sync_jobs
        register_sync_jobs(
            mediator=container.mediator(),
            job_scheduler=container.job_scheduler(),
        )
        logger.info("background_jobs_enabled")
```

### Health Check Route

```python
# In register_routes() or separate
def register_routes(app: FastAPI, settings, container: AppContainer) -> None:
    health_coordinator = container.health_coordinator()
    health_coordinator.register("database", check_database)
    health_coordinator.register("redis", check_redis)

    @app.get("/health")
    async def health_check() -> dict:
        result = await health_coordinator.check_all()
        result["version"] = settings.app_version
        result["environment"] = settings.environment
        return result
    ...
```

### Health Check Functions Update

```python
# src/common/health/checks.py
# Currently these likely call Database/Cache statically
# Update to accept instances or use container

async def check_database() -> dict:
    """Health check for MongoDB -- uses default Database instance."""
    # Option A: Accept database param (requires HealthCoordinator change)
    # Option B: Keep using backward compat (if still available)
    # Option C: Use container directly
    # Decision: Keep simple -- health checks are registered with closures
    ...
```

Better approach: register health checks with closures that capture container instances:

```python
def register_routes(app: FastAPI, settings, container: AppContainer) -> None:
    health_coordinator = container.health_coordinator()
    db = container.database()
    cache_instance = container.cache()

    async def check_db() -> dict:
        await db.get_database().command("ping")
        return {"latency_ms": ...}

    async def check_redis() -> dict:
        await cache_instance.get_client().ping()
        return {"latency_ms": ...}

    health_coordinator.register("database", check_db)
    health_coordinator.register("redis", check_redis)
    ...
```

## Related Code Files

| File | Action | Notes |
|------|--------|-------|
| `src/main.py` | modify | Refactor lifespan to use container init/shutdown |
| `src/main_extensions.py` | modify/delete | Remove `init_trading_subsystem()`, `start_background_jobs()`, `ensure_all_indexes()`. Keep `configure_middleware()`, `register_routes()`, `handle_startup_failure()` |
| `src/common/mediator/dependencies.py` | modify | Resolve from container instead of `app.state.mediator` |
| `src/common/health/checks.py` | modify | Closure-based health checks using container instances |
| `src/application/market_data/bar_manager.py` | modify | Inject Cache instance (remove static `Cache.set()` calls) |
| `src/application/market_data/quote_service.py` | modify | Inject Cache instance |

## Implementation Steps

1. **Update `src/common/mediator/dependencies.py`**:
   - Change `get_mediator()` to resolve from `request.app.state.container.mediator()`
   - All routes using `Depends(get_mediator)` continue to work unchanged

2. **Refactor `src/main.py` lifespan**:
   - Remove manual `Database.connect()`, `Cache.connect()` calls
   - Replace with `await container.init_resources()`
   - Remove manual shutdown calls
   - Replace with `await container.shutdown_resources()`
   - Call `ensure_all_indexes(container)` after init
   - Call `register_all_handlers(container)` after init
   - Call `register_background_jobs(container)` after init

3. **Refactor `src/main.py` `create_app()`**:
   - Create `AppContainer()` first
   - Store on `app.state.container`
   - Remove `app.state.mediator`, `app.state.event_bus`
   - Pass container to `register_routes()` for health checks

4. **Simplify `src/main_extensions.py`**:
   - Remove `ensure_all_indexes()` (moved to main.py or lifespan helper)
   - Remove `start_background_jobs()` (replaced by `register_background_jobs()`)
   - Remove `init_trading_subsystem()` (replaced by container)
   - Keep `configure_middleware()` (pure app config, no DI)
   - Keep `register_routes()` but update to accept container for health checks
   - Keep `handle_startup_failure()` (utility)

5. **Update health check functions**:
   - `check_database` and `check_redis` in `src/common/health/checks.py`
   - Use closure pattern capturing Database/Cache instances from container

6. **Inject Cache into remaining callers**:
   - `bar_manager.py` -- add Cache to constructor, remove static import
   - `quote_service.py` -- add Cache to constructor, remove static import
   - Register BarManager, QuoteService in container if not already done

7. **Remove `app.state` usage**:
   - Remove `app.state.mediator = mediator`
   - Remove `app.state.event_bus = event_bus`
   - Remove `app.state.strategy_engine = strategy_engine`
   - Remove `app.state.order_manager = order_manager`
   - Remove `app.state.position_tracker = position_tracker`
   - Only `app.state.container` remains

8. **Final cleanup**:
   - Remove any unused imports across all modified files
   - Remove backward-compat code added in Phase 2 (if not already done in Phase 4)
   - Verify no static `Database.xxx()` / `Cache.xxx()` / `JobScheduler.xxx()` calls remain

9. **Update docs**:
   - `docs/system-architecture.md` -- update "Singleton Infrastructure" section
   - `docs/code-standards.md` -- update patterns section, add DI pattern docs

10. **Run full validation**:
    - `ruff check src/`
    - `ruff format src/`
    - `pyright src/`
    - `pytest`

## Todo List

- [ ] Update `get_mediator()` to resolve from container
- [ ] Refactor `main.py` lifespan to use `container.init_resources()` / `shutdown_resources()`
- [ ] Refactor `create_app()` to create container, store on `app.state.container`
- [ ] Remove all `app.state.xxx` except `app.state.container`
- [ ] Update `register_routes()` to accept container for health checks
- [ ] Update health check functions to use injected instances
- [ ] Remove `init_trading_subsystem()` from main_extensions
- [ ] Remove `start_background_jobs()` from main_extensions
- [ ] Remove `ensure_all_indexes()` from main_extensions
- [ ] Inject Cache into `bar_manager.py` and `quote_service.py`
- [ ] Remove all remaining static `Database.xxx()` / `Cache.xxx()` / `JobScheduler.xxx()` calls
- [ ] Remove backward-compat `_default_instance` from BaseRepository
- [ ] Clean up unused imports
- [ ] Update `docs/system-architecture.md` DI section
- [ ] Update `docs/code-standards.md` patterns section
- [ ] Run `ruff check src/` + `ruff format src/`
- [ ] Run `pyright src/`
- [ ] Run full `pytest` suite
- [ ] Manual smoke test: start app, hit `/health`, sync a symbol

## Success Criteria

- **Zero `app.state` service locator** usage (only `app.state.container`)
- **Zero static singleton calls** to Database, Cache, JobScheduler in application code
- `main.py` lifespan is clean: init_resources -> post-init -> yield -> shutdown_resources
- All routes resolve dependencies via `Depends()` pulling from container
- Health check endpoint works
- Background jobs register and fire
- All tests pass
- Lint, format, type check clean

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Missed static call somewhere | Medium | `grep -r "Database\." src/`, `grep -r "Cache\." src/`, `grep -r "JobScheduler\." src/` |
| container.init_resources() fails mid-way | High | Resource generators handle cleanup; container rolls back initialized resources |
| Race condition: route hit before init completes | Low | FastAPI lifespan blocks requests until yield |
| Test fixtures depend on static singletons | Medium | Update all fixtures to use container or mock instances |
| Docs out of sync | Low | Update arch + code-standards docs in this phase |

## Security Considerations

- No credential handling changes
- `app.state.container` exposes all services -- ensure not serializable/loggable
- Health endpoint does not expose internal state

## Final Checklist (Post Phase 5)

After all 5 phases complete, verify:

- [ ] `src/container.py` is the single source of truth for all service wiring
- [ ] No module-level mutable globals remain (except `app = create_app()`)
- [ ] `main_extensions.py` contains only `configure_middleware()`, `register_routes()`, `handle_startup_failure()`
- [ ] All 7 repositories are instance-based with Database injected
- [ ] All ~27 handlers have explicit constructor dependencies
- [ ] EventBus, Mediator, HealthCoordinator are container Singletons
- [ ] Database, Cache, JobScheduler, OrderManager, PositionTracker, StrategyEngine are container Resources
- [ ] `docs/system-architecture.md` and `docs/code-standards.md` updated
- [ ] Full test suite green
- [ ] App starts, serves requests, shuts down gracefully
