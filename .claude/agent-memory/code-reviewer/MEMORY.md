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

### Layer Structure (post-DDD-restructure 2026-03-15)
```
src/domain/
  bar/               # entities.py, events.py, value_objects.py, services/bar_builder.py
  order/             # entities.py, enums.py, events.py
  position/          # entities.py, enums.py, events.py, value_objects.py
  symbol/            # entities.py
  sync_status/       # entities.py (extracted from bar/entities.py)
  backtest/          # entities.py (BacktestResult, OptimizationResult), value_objects.py, services/
  shared/            # enums.py (Interval), events.py (DomainEvent), value_objects.py (Symbol VO, INTERVAL_SECONDS)
  concepts/
    quote/           # events.py, value_objects.py
    risk/            # enums.py, value_objects.py, services/position_sizer.py
    strategy/        # enums.py, events.py, interfaces.py, value_objects.py, services/ma_crossover.py
src/application/     # Orchestrators: strategy_engine, order_manager, position_tracker, bar_manager, sync_jobs, backtest_runner
src/persistence/     # Top-level: Database, Cache, BaseRepository, 7 repos
src/infrastructure/  # I/O: brokers/, tradingview/, webhooks/
src/features/        # Thin CQRS: commands, queries, handlers, routes, DTOs
src/common/          # Cross-cutting: mediator, messaging, logging, cache, database, jobs
```

### Dependency Rules
- features -> application -> domain (allowed)
- features/application -> persistence (repos) (allowed)
- infrastructure -> domain, persistence (allowed)
- persistence -> domain, common (BacktestResult/OptimizationResult now in domain -- upward dep fixed)
- domain -> nothing except src.common utilities
- common/database and common/cache are re-export shims -> src.persistence

### Key Files
- `src/main.py` - App lifespan, DI composition root, router inclusion, index creation
- `src/persistence/base_repository.py` - BaseRepository mixin (single Database.get_collection call)
- `src/persistence/repositories/` - 7 repos: Bar, SyncStatus, Symbol, Optimization, Order, Position, Backtest
- `src/di/` - 6 dishka providers (Core, Persistence, Infrastructure, MarketData, Trading, Handler)
- `src/main_extensions.py` - Middleware, routes, ensure_all_indexes()
- `src/common/mediator/` - CQRS mediator + HandlerRegistry
- `src/common/messaging/` - EventBus + EventRegistry for domain events

### Known Issues (as of 2026-03-15)
- **[CRITICAL] Backtest routes call `.to_dict()` but classes only have `.to_mongo()`** -- 4 routes broken
- **Two `Symbol` classes**: shared VO (`shared/value_objects.Symbol`) vs entity (`symbol/entities.Symbol`) -- naming collision risk
- `market_data/__init__.py` still thin (just docstring), no facade re-exports
- `RiskCheckHandler` in features is actually a domain/application service, not a CQRS handler
- `common/database`, `common/cache`, `infrastructure/__init__` all re-export from persistence -- 3 import paths for same classes
- `Interval` importable from both `shared.enums` and `shared.value_objects` (backward compat re-export)
- `strategy/services/__init__.py` is empty (should re-export MACrossoverStrategy)
- **`SyncStatusRepository.find_all()` and `SymbolRepository.find_all()` unbounded** -- no `.limit()`
- **Positions missing compound index (strategy_id, is_closed)** -- inefficient query
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
- `plans/reports/code-reviewer-260315-1740-ddd-folder-restructure.md` - DDD folder restructure review (1 critical: broken to_dict)
