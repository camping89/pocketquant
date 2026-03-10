# Planner Agent Memory

## Project: PocketQuant

### Architecture
- Clean Architecture + DDD + CQRS + Vertical Slice
- Layer order: Features -> Application -> Domain; Infrastructure -> Domain
- ~14,400 LOC across 213 files (182 Python in src/)
- Python 3.14+, FastAPI, MongoDB (pymongo async), Redis, APScheduler

### Key Patterns
- CQRS: `@handles` decorator + `HandlerRegistry.register_all()` in per-feature `register.py`
- Events: `@event_handler` decorator + `EventBus` (in-memory FIFO)
- Repos: 7 repositories in `src/persistence/repositories/`, all inherit `BaseRepository`
- Static singletons: Database, Cache, JobScheduler use class-method pattern (being migrated to DI)
- Routes use `Depends(get_mediator)` via `src/common/mediator/dependencies.py`
- Re-exports: `src/common/database/` -> `src/persistence/`, `src/common/cache/` -> `src/persistence/`

### File Conventions
- Python snake_case, kebab-case for non-Python
- Files under 200 LOC target
- Structured logging via `get_logger(__name__)`
- Type hints everywhere, pyright for type checking, ruff for lint

### Plans Location
- Plans dir: `plans/` with `{YYMMDD}-{HHMM}-{slug}/` naming
- Reports dir: `plans/reports/` or `plans/{plan-name}/reports/`

### Tooling
- Package manager: uv
- Task runner: just (justfile)
- Tests: pytest + pytest-asyncio
- Lint: ruff check, Format: ruff format, Types: pyright

### Domain Layer Structure
- 5 aggregates: Order, Position, Symbol, Quote, OHLCV
- Some domain files already use dataclasses: `Bar`, `SyncStatus`, `BarBuilder`, `StrategyConfig`, `StopLossConfig`, `TakeProfitConfig`, `OrderConfig`
- Persistence schemas (Pydantic) map to/from aggregates via `from_aggregate()`/`to_aggregate()` with explicit enum conversion
- Only `OrderDocument` and `PositionDocument` reference aggregates directly; symbol/quote/ohlcv schemas have own models
- Domain purity enforced via `test_domain_purity.py` (AST check)
- Two event collection patterns exist: `collect_events()` vs `get_uncommitted_events()`+`clear_events()`

### Active Plans
- DI container refactor: `plans/260215-0956-dependency-injection-container/`
- Domain Pydantic->dataclass refactor: `plans/260309-0918-domain-pydantic-to-dataclass-refactor/`
