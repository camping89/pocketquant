# Code Reviewer Agent Memory

## Project: PocketQuant

### Architecture Pattern (updated 2026-02-14)
- **Clean Architecture** with 4 layers: Domain -> Application -> Features -> Infrastructure
- **CQRS**: Operations split into `command.py` + `handler.py` + `route.py` (commands) or `query.py` + `handler.py` + `route.py` (queries)
- **Each operation folder**: `__init__.py` (re-exports), `handler.py`, `query.py`/`command.py`, `route.py`
- **Feature `__init__.py`**: Facade re-exports for public API surface with `__all__`
- **Cross-feature imports**: Use `TYPE_CHECKING` guards to prevent circular deps
- **Handler registration**: `register.py` per feature, `@handles` decorator, `HandlerRegistry` auto-registration
- **Event handlers**: `@event_handler` decorator + `EventRegistry` for auto-discovery

### Layer Structure (post-persistence-refactor 2026-02-14)
```
src/domain/          # Pure: value objects, aggregates, events, interfaces, domain services
src/application/     # Orchestrators: strategy_engine, order_manager, position_tracker, bar_manager, sync_jobs, backtest_runner
src/persistence/     # Top-level: Database, Cache, BaseRepository, 7 repos, schemas
src/infrastructure/  # I/O: brokers/, tradingview/, webhooks/ (persistence moved out)
src/features/        # Thin CQRS: commands, queries, handlers, routes, DTOs, register.py, router.py
src/common/          # Cross-cutting: mediator, messaging, logging, cache (re-export shim), database (re-export shim), jobs
```

### Dependency Rules
- features -> application -> domain (allowed)
- features/application -> persistence (repos, schemas) (allowed)
- infrastructure -> domain, persistence.schemas (allowed)
- persistence -> domain, common, application.models (2 accepted exceptions: BacktestResult, OptimizationResult)
- domain -> nothing except src.common utilities
- common/database and common/cache are re-export shims -> src.persistence

### Key Files
- `src/main.py` - App lifespan, DI composition root, router inclusion, index creation
- `src/persistence/base_repository.py` - BaseRepository mixin (single Database.get_collection call)
- `src/persistence/repositories/` - 7 repos: OHLCV, SyncStatus, Symbol, Optimization, Order, Position, Backtest
- `src/container.py` - DI container (AppContainer), replaces per-feature register.py
- `src/main_extensions.py` - Middleware, routes, ensure_all_indexes()
- `src/common/mediator/` - CQRS mediator + HandlerRegistry
- `src/common/messaging/` - EventBus + EventRegistry for domain events

### Known Issues (as of 2026-02-15)
- `market_data/__init__.py` still thin (just docstring), no facade re-exports
- `RiskCheckHandler` in features is actually a domain/application service, not a CQRS handler
- Domain purity test missing `src.application`, `src.features`, `fastapi` in FORBIDDEN_IMPORTS
- `persistence -> application` upward deps: backtest_repository imports BacktestResult, optimization_repository imports OptimizationResult
- `common/database`, `common/cache`, `infrastructure/__init__` all re-export from persistence -- 3 import paths for same classes
- `SymbolRepository.find_all()` returns `list[dict]` not typed `Symbol` model -- breaks repo pattern
- **OHLCV compound index missing `unique=True`** -- risk of duplicate bars
- **`SyncStatusRepository.find_all()` and `SymbolRepository.find_all()` unbounded** -- no `.limit()`
- **BulkSyncHandler and sync_jobs serial N+1** -- should parallelize with semaphore
- **BarManager._save_completed_bar() doesn't invalidate OHLCV cache** -- stale reads for 300s
- **SymbolRepository.upsert() doesn't normalize case** -- relies on caller
- **OHLCVRepository.stream() redundant Interval conversion** -- `from_mongo()` already handles it
- **Positions missing compound index (strategy_id, is_closed)** -- inefficient query
- **No BulkWriteError handling in upsert_many()** -- partial failures silently pass
- **MongoDB returns naive datetimes** -- could cause TypeError if compared with aware datetimes
- **OrderManager._orders dict grows unboundedly** -- no eviction for completed orders

### Tech Stack
- Python 3.14, FastAPI, Pydantic, structlog, MongoDB (pymongo native async), Redis, APScheduler
- Type checking: pyright (0 errors as of 2026-02-14)
- Linting: ruff (42 issues, 41 auto-fixable -- mostly import sorting)
- Tests: pytest + pytest-asyncio (60 tests passing)

### DI Pattern (updated 2026-03-13)
- [project_dishka_di.md](project_dishka_di.md) -- dishka provider structure, DishkaRoute propagation gotcha

### Review Reports
- `plans/reports/code-review-260214-persistence-layer.md` - Persistence layer extraction review
- `plans/reports/code-review-260214-clean-architecture-refactor.md` - Full clean arch refactor review
- `plans/reports/code-reviewer-260214-1331-mediator-auto-discovery.md` - Mediator decorator review
- `plans/reports/code-reviewer-260213-0127-vertical-slice-review.md` - Vertical slice review
- `plans/reports/code-reviewer-260215-1908-database-layer-review.md` - Database layer deep dive (12 categories)
- `plans/reports/code-review-260313-1243-dishka-migration.md` - Dishka DI migration review (critical DishkaRoute bug)
