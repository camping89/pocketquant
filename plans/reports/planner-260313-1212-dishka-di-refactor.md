# Planner Report: Dishka DI Migration

**Date**: 2026-03-13
**Plan**: `plans/260313-1212-dishka-di-refactor/`
**Status**: Complete (plan created, ready for implementation)

## Summary

Created 5-phase plan to migrate PocketQuant from plain Python constructor DI (frozen `Services` dataclass + 118-line manual handler registration) to **dishka** async-first DI framework.

## Key Decisions

1. **All services APP-scoped** — no REQUEST scope needed currently (routes just dispatch to Mediator singleton)
2. **7 provider classes** organized by domain: Config, Persistence, Messaging, Infrastructure, MarketData, Trading, Handlers
3. **Generator factories** for async lifecycle (Database, Cache, JobScheduler, StrategyEngine) — dishka handles cleanup in reverse order
4. **DishkaRoute on parent routers** for automatic `FromDishka[]` injection — avoids `@inject` on every route
5. **Handler registration** stays explicit: lifespan resolves all 28 handlers from container, registers with Mediator via existing `HandlerRegistry`
6. **Middleware hot-path** unchanged: `app.state.cache`/`app.state.database` still set for IdempotencyMiddleware and RateLimitMiddleware
7. **BacktestRunner/GridOptimizer** stay manual (created fresh per handler call, not singletons)

## Estimated Effort

| Phase | Effort |
|-------|--------|
| 1. Install + create 8 provider files | 2h |
| 2. Migrate lifespan + create container.py | 1.5h |
| 3. Update 27 route files to FromDishka | 1h |
| 4. Delete 3 dead files (~222 LOC) | 0.5h |
| 5. Update tests + add container validation | 1h |
| **Total** | **6h** |

## Files Created

- `plans/260313-1212-dishka-di-refactor/plan.md` — overview + phase index
- `plans/260313-1212-dishka-di-refactor/phase-01-create-providers.md` — provider code patterns
- `plans/260313-1212-dishka-di-refactor/phase-02-migrate-lifespan.md` — lifespan rewrite
- `plans/260313-1212-dishka-di-refactor/phase-03-update-routes.md` — route migration (27 files)
- `plans/260313-1212-dishka-di-refactor/phase-04-delete-dead-code.md` — cleanup
- `plans/260313-1212-dishka-di-refactor/phase-05-update-tests.md` — test updates

## Open Items for Implementation

1. **Verify `DishkaRoute` propagation**: Does setting `route_class=DishkaRoute` on parent router propagate to sub-routers included via `include_router()`? If not, fall back to `@inject` decorator per route.
2. **`setup_dishka` placement**: Check whether it should be called in `create_app()` (before lifespan) or inside lifespan (after container is ready). Dishka FastAPI docs are the authority.
3. **Repository constructors**: Confirm all 7 repos take only `database: Database` in `__init__` before using `provide(RepoClass, scope=Scope.APP)` shorthand.
4. **`JobScheduler` generator**: The `get_job_scheduler` factory is sync but uses `yield` — verify dishka supports sync generators for APP scope, or make it async.
