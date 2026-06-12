---
name: dishka_di_migration
description: Dishka DI pattern -- provider layout per process, DishkaRoute gotcha, silent duplicate-provider behavior
metadata:
  type: project
---

DI uses dishka. Two containers as of 2026-06: `app/di/container.py` (7 providers: Core, Persistence, Infrastructure, Execution, MarketData, AppTradingService, BacktestWorker) and `bff/di/` (near-copy minus execution/worker, plus `BffServiceProvider` in `bff/di/services.py`).

**How to apply:**
- All feature services Scope.APP, stateless; generator factories (yield) = connect/disconnect lifecycle via container.close()
- DishkaRoute does NOT propagate to child routers via include_router() -- each leaf router needs it
- **Duplicate `provide(X)` across providers passed to `make_async_container` is accepted SILENTLY (last provider wins)** -- verified empirically 2026-06-11. When merging/union-ing providers, dedup manually; dishka will not flag the overlap.
- Admin auth is a route-level `Depends(verify_admin_token)` dependency (`bff/middleware/admin_auth_middleware.py`), NOT middleware in `configure_middleware` -- reviews claiming "middleware order" for auth are mischaracterized.
