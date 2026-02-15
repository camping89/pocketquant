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

### Active Plans
- DI container refactor: `plans/260215-0956-dependency-injection-container/`
