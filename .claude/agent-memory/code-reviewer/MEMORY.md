# Code Reviewer Agent Memory

## Project: PocketQuant

### Architecture Pattern (updated 2026-06-11, Phase 4 "kill mediator", a33917d..ea8f431)
- **Clean Architecture**; CQRS Mediator DELETED — no `@handles`, no `Mediator.send()`, no dir-per-endpoint command/handler/route triplets
- **Feature services**: one class per feature area (`SyncService`, `StrategyCommandService`, `BacktestQueryService`, ...); command/query DTOs live in service module, class names preserved as public contract
- **Routes**: flat modules `bff/routes/*.py`, inject via `FromDishka[XxxService]` + `DishkaRoute` (CLAUDE.md "FromDishka[Mediator]" rule stale until Phase 5 docs sync)
- **DI**: `bff/di/services.py` (BffServiceProvider) + `app/di/trading_services.py`/`market_data.py` — all Scope.APP, services stateless
- **Scheduler jobs**: module-level container ref, `container.get(SyncService)`; APScheduler text func refs unchanged
- **Event handlers**: `@event_handler` + `EventRegistry` still exist (EventBus untouched)
- `OrderPositionQueryService` only in app DI; its routes also mounted in bff → bff 500s by design (matches old handler-exclusion behavior)
- Mediator deletion side effect: query routes that returned `result.to_dict()` after `if not result: raise NotFoundError` now raise NotFoundError inside service — same 404, but NoFactoryError from dishka replaces old HandlerNotFoundError for unregistered services (both → 500)

### Layer Structure (post Phase 2 lean-monorepo collapse, 2026-06-10)
Single package `pocketquant` at root `src/` (PEP 420 namespace — no `__init__.py` at `src/pocketquant/`). Subpackage `execution` renamed `engine`. uv workspace dissolved.
```
src/pocketquant/
  core/      # 0 internal deps — core/domain (entities/VOs/ports; ex-concepts quote/risk/strategy merged in), core/infra (persistence, brokers/paper, binance, scheduling, http_client — Phase 3 reshape 2026-06-10), core/common, config
             # import-linter: core.domain forbidden from core.infra; test_domain_purity FORBIDDEN_IMPORTS has "pocketquant.core.infra"
             # layout guard: tests/core_test/test_core_layout_contract.py (dead-module imports + stale "core.<old>" fragment scan, .py-only)
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
