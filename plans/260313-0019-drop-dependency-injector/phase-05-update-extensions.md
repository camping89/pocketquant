# Phase 5: Update main_extensions.py

**Priority:** Medium | **Status:** Pending | **Effort:** S

## Overview

Remove all `container` and `resolve()` references from `main_extensions.py`. Functions now accept `Services` instead of `AppContainer`.

## Context Links

- Current: `src/main_extensions.py` (143 LOC)
- Uses `resolve()` for repos and job_scheduler

## Implementation Steps

1. Update `ensure_all_indexes()`:

```python
# Before
async def ensure_all_indexes(container: AppContainer) -> None:
    repos = await asyncio.gather(
        *(resolve(getattr(container, name)) for name in _REPO_PROVIDERS)
    )
    await asyncio.gather(*(repo.ensure_indexes() for repo in repos))

# After
async def ensure_all_indexes(services: Services) -> None:
    repos = [
        services.order_repository,
        services.position_repository,
        services.backtest_repository,
        services.ohlcv_repository,
        services.sync_status_repository,
        services.symbol_repository,
        services.optimization_repository,
    ]
    await asyncio.gather(*(repo.ensure_indexes() for repo in repos))
```

2. Update `start_background_jobs()`:

```python
# Before
async def start_background_jobs(container: AppContainer) -> None:
    settings = container.settings()
    if settings.enable_jobs:
        register_sync_jobs(
            mediator=container.mediator(),
            job_scheduler=await resolve(container.job_scheduler),
            sync_status_repo=await resolve(container.sync_status_repository),
        )

# After
async def start_background_jobs(services: Services) -> None:
    if services.settings.enable_jobs:
        register_sync_jobs(
            mediator=services.mediator,
            job_scheduler=services.job_scheduler,
            sync_status_repo=services.sync_status_repository,
        )
```

3. Update `register_routes()`:

```python
# Before
def register_routes(app: FastAPI, container: AppContainer, settings) -> None:
    health_coordinator = container.health_coordinator()
    # ...
    scheduler = await resolve(app.state.container.job_scheduler)

# After
def register_routes(app: FastAPI, settings) -> None:
    # Health checks use app.state at runtime (services set during lifespan)
    async def _check_db() -> dict:
        return await check_database(app.state.database)
    async def _check_redis() -> dict:
        return await check_redis(app.state.cache)

    # Health coordinator registered lazily via startup event or lifespan
    # ... (see implementation notes below)
```

4. Remove imports: `from src.container import AppContainer, resolve`
5. Remove `_REPO_PROVIDERS` string list
6. Add import: `from src.services import Services`

## Implementation Note: Health Coordinator

Current code calls `container.health_coordinator()` in `register_routes()` which runs BEFORE lifespan. Two options:

**Option A (simple):** Move health check registration into lifespan, after Services is built.
**Option B (keep current):** Pass `health_coordinator` to `register_routes()` separately.

Recommend **Option A** — health coordinator is in Services, register checks after services are built in lifespan.

## Implementation Note: /system/jobs endpoint

Current code uses `await resolve(app.state.container.job_scheduler)`. Replace with:
```python
@api.get("/system/jobs")
async def list_jobs(request: Request) -> list[dict]:
    return request.app.state.services.job_scheduler.get_jobs()
```

## Todo

- [ ] Update `ensure_all_indexes(services)` — direct repo access
- [ ] Update `start_background_jobs(services)` — direct service access
- [ ] Update `register_routes()` — remove container param
- [ ] Move health check registration to lifespan
- [ ] Update /system/jobs endpoint
- [ ] Remove `resolve` and `AppContainer` imports
- [ ] Remove `_REPO_PROVIDERS` string list

## Success Criteria

- Zero `resolve()` calls in codebase
- Zero `AppContainer` references outside deleted `container.py`
- All extension functions accept `Services` type
