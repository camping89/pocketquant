# Code Review: Dishka DI Migration

**Date:** 2026-03-13
**Branch:** `feat/strategy-init`
**Scope:** Dishka DI integration replacing manual Services dataclass + handler_registration.py
**Files reviewed:** 12 (6 providers, container.py, main.py, main_extensions.py, 5 sample routes)

---

## Overall Assessment

The provider decomposition and lifecycle management are well-designed -- clean separation, idiomatic generator factories for cleanup, and good documentation. However, there is one **critical blocker**: the app cannot start due to `DishkaRoute` not propagating to child routers. Every feature route using `FromDishka` crashes at import time.

---

## Critical Issues

### 1. App crashes on startup -- DishkaRoute does not propagate to child routers

**Severity:** CRITICAL (app cannot start)
**Verified:** `python -c "from src.main import create_app"` throws `FastAPIError`

`main_extensions.py:144` sets `route_class=DishkaRoute` on the parent `api` APIRouter:
```python
api = APIRouter(prefix=settings.api_prefix, route_class=DishkaRoute)
api.include_router(market_data_router)  # child has no DishkaRoute
```

But FastAPI does NOT propagate `route_class` to child routers added via `include_router()`. When a child router (e.g., `trading/list_orders/route.py`) defines `router = APIRouter()` without `DishkaRoute`, and registers a route with `FromDishka[Mediator]`, FastAPI tries to parse `FromDishka[Mediator]` as a Pydantic field type -- which fails immediately.

`DishkaRoute` is just an `APIRoute` subclass that calls `inject(endpoint)` in its `__init__`. Without it, the `FromDishka` annotation is never unwrapped into a proper `Depends()`.

**Error:**
```
FastAPIError: Invalid args for response field! Hint: check that
typing.Annotated[src.common.mediator.mediator.Mediator, _FromComponent(component='')]
is a valid Pydantic field type.
```

**Why tests pass:** No test imports `src.main` or calls `create_app()`. Tests exercise handlers/mediator/services in isolation.

**Fix (two options, pick one):**

*Option A -- DishkaRoute on every leaf router (recommended, DRY with a helper):*
```python
# src/common/routing.py
from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

def create_router(**kwargs) -> APIRouter:
    """APIRouter pre-configured with DishkaRoute for dishka injection."""
    return APIRouter(route_class=DishkaRoute, **kwargs)
```
Then replace all `router = APIRouter()` in route files with `router = create_router()`.

*Option B -- `@inject` on every route endpoint:*
Add `@inject` decorator to each of the ~30 route functions. More verbose, no factory needed.

Option A is simpler: one import change per file, zero risk of forgetting `@inject` on new routes.

### 2. Missing integration test for app startup

**Severity:** CRITICAL (the above crash went undetected)

There is no test that even imports `src.main` or instantiates the FastAPI app. This means any wiring error -- DishkaRoute, missing provider, wrong scope -- is invisible to CI.

**Fix:** Add a minimal smoke test:
```python
# tests/integration/test_app_startup.py
def test_app_creates_without_error():
    """Verify all routes register without import-time crashes."""
    from src.main import create_app
    app = create_app()
    assert app is not None
```

---

## High Priority

### 3. Duplicate handler type list -- maintenance trap

`handler_provider.py` maintains two parallel lists of the same 27 handlers:
1. Class attributes with `provide(XHandler, scope=Scope.APP)` (lines 46-82)
2. `ALL_HANDLER_TYPES` list (lines 86-114)

Adding a handler requires updating both. Forgetting the second list means the handler is in the container but never registered with Mediator -- silent failure.

**Fix:** Derive `ALL_HANDLER_TYPES` automatically:
```python
# At bottom of handler_provider.py
ALL_HANDLER_TYPES: list[type] = [
    factory.provides.type_hint
    for factory in HandlerProvider.__dishka_factories__  # type: ignore[attr-defined]
]
```
Or simpler, introspect after class creation:
```python
import inspect
ALL_HANDLER_TYPES: list[type] = [
    attr.provides.type_hint
    for name, attr in vars(HandlerProvider).items()
    if hasattr(attr, 'provides')
]
```
This eliminates the duplication entirely.

### 4. "Add a handler" instructions incomplete

`src/providers/__init__.py` documents two steps but the actual process requires three:
1. Add `@handles(RequestType)` decorator
2. Add `provide(YourHandler, scope=Scope.APP)` in HandlerProvider
3. **Add handler type to `ALL_HANDLER_TYPES`** (missing from docs)

If issue #3 is fixed (auto-derive the list), step 3 disappears and the docs become correct.

### 5. Health check closures use `app.state` instead of resolved deps

`main_extensions.py:84-85`:
```python
hc.register("database", partial(check_database, app.state.database))
hc.register("redis", partial(check_redis, app.state.cache))
```

This works because `app.state.database` and `app.state.cache` are set on the line before. But it creates an implicit coupling between the health checks and `app.state` -- the same objects are available from the container. The container should be the single source of truth.

**Fix:** Resolve from container directly:
```python
async def register_health_checks(container: AsyncContainer) -> None:
    hc = await container.get(HealthCoordinator)
    database = await container.get(Database)
    cache = await container.get(Cache)
    hc.register("database", partial(check_database, database))
    hc.register("redis", partial(check_redis, cache))
```
This also removes the need for the `app` parameter.

---

## Medium Priority

### 6. `RiskCheckHandler` misplaced in InfrastructureProvider

`infrastructure_provider.py:37`:
```python
risk_handler = provide(RiskCheckHandler, scope=Scope.APP)
```

`RiskCheckHandler` is a domain/application service (validates trading signals against risk rules). It lives in `src/features/risk/check_risk/handler.py` and has zero infrastructure dependencies. Placing it in `InfrastructureProvider` is misleading.

**Fix:** Move to `TradingProvider` (since StrategyEngine depends on it) or create a thin `RiskProvider`. This is a known issue from prior reviews but worth calling out since the provider structure makes it more visible.

### 7. `handle_startup_failure` references wrong file path

`main_extensions.py:105`:
```python
console.print("  -> [cyan]src/common/database/connection.py[/] in connect")
```

This file doesn't exist. The actual database module is `src/persistence/mongodb.py`.

**Fix:** Update the path string to `src/persistence/mongodb.py`.

### 8. `os._exit(1)` in startup failure skips container cleanup

`handle_startup_failure` calls `os._exit(1)` which kills the process immediately, bypassing the `finally` block in `lifespan`. This means `container.close()` never runs -- database connections and the scheduler aren't cleanly shut down.

In practice this is acceptable for a startup crash (no connections are in active use yet). But if the failure happens late in startup (e.g., after DB connects but before indexes finish), the DB connection pool leaks.

**Recommendation:** Log and re-raise instead of `os._exit(1)`. Let the `finally` block handle cleanup:
```python
def handle_startup_failure(error: Exception) -> None:
    # ... rich panel output ...
    raise  # Let finally block run, then FastAPI exits cleanly
```

### 9. Stale imports in main.py

`main.py` imports `Database` and `Cache` at the top level (lines 20-21) but only uses them inside `lifespan`. These could be lazy imports or removed if the health check fix in #5 is applied (container resolves them directly).

Not a bug, just unnecessary top-level coupling.

---

## Low Priority

### 10. Provider ordering comment could be enforced

`container.py:23-24`:
```python
# Order matters: later providers may depend on earlier ones.
PROVIDERS = [CoreProvider(), PersistenceProvider(), ...]
```

Dishka actually resolves dependencies by type, not by provider order. The order doesn't matter for correctness -- dishka builds a dependency graph across all providers. The comment is misleading.

**Fix:** Remove the comment or clarify: "Providers are listed in dependency order for readability, but dishka resolves across all providers regardless of order."

### 11. `JobScheduler` generator has sync `shutdown()` in async generator

`infrastructure_provider.py:30`:
```python
scheduler.shutdown(wait=True)  # sync call in async generator teardown
```

`JobScheduler.shutdown()` is synchronous. Calling it in an async generator teardown context could block the event loop if APScheduler's shutdown takes time (e.g., waiting for running jobs).

**Recommendation:** Wrap in `asyncio.to_thread()` if shutdown can be slow:
```python
await asyncio.to_thread(scheduler.shutdown, wait=True)
```

### 12. `config_provider.py` and `messaging_provider.py` deleted but git shows them in earlier reads

Files are properly deleted and merged into `core_provider.py`. No stale references found. Clean migration.

---

## Answers to Specific Questions

### Is `container.get()` correct for APP scope?

**Yes.** `make_async_container()` returns a root container whose scope is `Scope.APP`. Calling `await container.get(Type)` on the root container resolves APP-scoped singletons directly. No `async with container:` needed -- that pattern is for creating child containers (REQUEST/SESSION scope). `container.close()` handles generator cleanup.

### Does `DishkaRoute` on the parent `api` router propagate to child sub-routers?

**No.** Verified experimentally. FastAPI `include_router()` copies routes from the child router using the child's own `route_class` (defaults to `APIRoute`). The parent's `route_class` only applies to routes defined directly on the parent (e.g., `/system/jobs`). See Critical Issue #1.

### Is the handler registration approach idiomatic for dishka?

**Partially.** Using `container.get()` in a loop to resolve handlers is correct but not the "dishka way." Idiomatic dishka would have routes use `FromDishka[Mediator]` and never manually resolve handlers. The current approach works because handlers are APP-scoped singletons that need to be pre-registered with Mediator at startup -- a legitimate pattern for mediator-based CQRS. The main issue is the duplicate list (see #3).

### Should `register_health_checks` be simplified?

**Yes.** See #5. Remove the `app` parameter, resolve Database/Cache from container instead of `app.state`. This also decouples health checks from the middleware hot-path pattern.

---

## Positive Observations

1. **Generator factories for lifecycle** -- `PersistenceProvider` and `TradingProvider` use async generators (`yield`) for connect/disconnect and start/stop. This is exactly how dishka lifecycle management is designed. Cleanup runs in reverse creation order when `container.close()` is called.

2. **Provider decomposition** -- Six providers split by domain concern (Core, Persistence, Infrastructure, MarketData, Trading, Handlers). Clean boundaries, no circular dependencies between providers.

3. **CoreProvider consolidation** -- Merging Settings/EventBus/Mediator into one provider with good docstring was the right call. These are simple stateless singletons.

4. **Auto-resolution for repositories** -- `provide(OHLCVRepository, scope=Scope.APP)` lets dishka inspect `BaseRepository.__init__(database: Database)` and auto-wire. Zero boilerplate.

5. **Explicit handler factories for complex init** -- `TradingProvider.get_order_manager()` calls `await manager.load_pending_orders()` after construction. This cannot be expressed with auto-resolution alone, and the factory pattern is the correct approach.

6. **Clean deletion** -- `services.py`, `dependencies.py`, `handler_registration.py` all removed with no stale imports.

---

## Recommended Actions (Priority Order)

1. **[CRITICAL]** Fix DishkaRoute propagation -- create `create_router()` helper, update all leaf route files
2. **[CRITICAL]** Add integration test that calls `create_app()` to catch wiring errors
3. **[HIGH]** Auto-derive `ALL_HANDLER_TYPES` from `HandlerProvider` class attributes
4. **[HIGH]** Update "Adding a handler" docs in `__init__.py`
5. **[MEDIUM]** Simplify `register_health_checks` to resolve from container
6. **[MEDIUM]** Fix stale file path in `handle_startup_failure`
7. **[LOW]** Clarify provider ordering comment
8. **[LOW]** Consider `asyncio.to_thread` for sync shutdown calls

---

## Unresolved Questions

1. **Should `app.state.database` and `app.state.cache` be kept?** They exist for "middleware hot-path access" but it's unclear which middleware uses them directly. If only health checks use them, remove the `app.state` assignment entirely after applying fix #5.

2. **Should `RiskCheckHandler` move to `src/domain/risk/` or `src/application/`?** It has no CQRS semantics and no infrastructure deps. Its current location in `features/risk/` with registration in `InfrastructureProvider` is a double mismatch.

3. **Is `StrategyEngine.__init__` with `TYPE_CHECKING` guards compatible with dishka auto-resolution?** Currently safe because `TradingProvider` uses an explicit factory. But if someone tries `provide(StrategyEngine, scope=Scope.APP)` instead, dishka will fail to inspect the `__init__` type hints at runtime (they're strings under `TYPE_CHECKING`).
