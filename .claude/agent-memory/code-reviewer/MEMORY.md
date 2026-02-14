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

### Layer Structure (post-refactor 2026-02-14)
```
src/domain/          # Pure: value objects, aggregates, events, interfaces, domain services
src/application/     # Orchestrators: strategy_engine, order_manager, position_tracker, bar_manager, sync_jobs, backtest_runner
src/infrastructure/  # I/O: persistence/ (schemas, repositories), brokers/, tradingview/, webhooks/
src/features/        # Thin CQRS: commands, queries, handlers, routes, DTOs, register.py, router.py
src/common/          # Cross-cutting: mediator, messaging, logging, cache, database, jobs
```

### Dependency Rules
- features -> application -> domain (allowed)
- infrastructure -> domain (allowed)
- domain -> nothing except src.common utilities
- 3 accepted exceptions documented in review report

### Key Files
- `src/main.py` - App lifespan, DI composition root, router inclusion
- `src/features/*/register.py` - Handler registration with mediator
- `src/common/mediator/` - CQRS mediator + HandlerRegistry
- `src/common/messaging/` - EventBus + EventRegistry for domain events

### Known Issues (as of 2026-02-14)
- `market_data/__init__.py` still thin (just docstring), no facade re-exports
- Application layer has direct `Database.get_collection` calls (bar_manager, sync_jobs, backtest_runner) -- should use repos
- `RiskCheckHandler` in features is actually a domain/application service, not a CQRS handler
- Domain purity test missing `src.application`, `src.features`, `fastapi` in FORBIDDEN_IMPORTS
- Orphan dir: `src/features/market_data/repositories/` (only pycache, no Python files)
- `sync_jobs.py` uses module-global `_mediator` (service locator anti-pattern)
- Feature handlers in market_data have direct `Database.get_collection` calls (no repos for OHLCV/sync-status/symbols)

### Tech Stack
- Python 3.14, FastAPI, Pydantic, structlog, MongoDB (pymongo native async), Redis, APScheduler
- Type checking: pyright (0 errors as of 2026-02-14)
- Linting: ruff (42 issues, 41 auto-fixable -- mostly import sorting)
- Tests: pytest + pytest-asyncio (60 tests passing)

### Review Reports
- `plans/reports/code-review-260214-clean-architecture-refactor.md` - Full clean arch refactor review
- `plans/reports/code-reviewer-260214-1331-mediator-auto-discovery.md` - Mediator decorator review
- `plans/reports/code-reviewer-260213-0127-vertical-slice-review.md` - Vertical slice review
