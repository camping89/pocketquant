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

### Layer Structure (post Phase 2 lean-monorepo collapse, 2026-06-10)
Single package `pocketquant` at root `src/` (PEP 420 namespace — no `__init__.py` at `src/pocketquant/`). Subpackage `execution` renamed `engine`. uv workspace dissolved.
```
src/pocketquant/
  core/      # 0 internal deps — domain, config, ports+DTOs, persistence (Database/Cache/repos), PaperBroker, binance, scheduling, mediator, messaging
  engine/    # -> core — shared strategy/order/position/risk app services + market_data sync jobs/handlers
  backtest/  # -> core, engine
  trading/   # -> core, engine — OKX broker
  app/       # -> all — headless runtime (scheduler, WS feed, reconcile, backtest worker)
  bff/       # -> core, backtest, trading — stateless FE gateway
packages/pocketquant-web/  # Node SPA, only survivor of packages/
```
- One root pyproject.toml (hatchling, `packages=["src/pocketquant"]`), import-linter contracts enforce layers
- Tests: `tests/{core,engine,backtest,trading,app,bff}_test` + `tests/baseline` (OpenAPI/route/mediator snapshots + layout contract); root `tests/conftest.py` = single source for env seeding + prod-DB guard (`207.148.79.60` fragment); per-suite conftests fixture-only
- APScheduler MongoDBJobStore (`apscheduler_jobs` collection) persists pickled text func refs `pocketquant.engine.market_data.app_services.sync_jobs:<fn>`; apscheduler 3.11 `_get_jobs` auto-deletes unrestorable jobs, `replace_existing=True` update_job rewrites job_state — module renames self-heal at boot (verified from installed source 2026-06-10)

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
