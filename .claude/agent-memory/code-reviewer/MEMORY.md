# Code Reviewer Agent Memory

## Project: PocketQuant

### Architecture Pattern (updated 2026-06-11, 4-subpackage single-process refactor, 23feaa2..53da61f+Phase4)
- **Clean Architecture**; CQRS Mediator DELETED — no `@handles`, no `Mediator.send()`
- **Feature services**: one class per feature area (`SyncService`, `StrategyCommandService`, `BacktestQueryService`, ...); command/query DTOs live in service module, class names preserved as public contract
- **Routes**: flat modules `app/routes/*.py`, inject via `FromDishka[XxxService]` + `DishkaRoute`
- **DI**: all providers in `src/pocketquant/app/di/` — `services.py` (ServicesProvider, route-facing), `trading_services.py` (Strategy*/OrderPosition), `market_data.py` (SyncService + runtime). SyncService/StrategyCommandService/StrategyQueryService each registered EXACTLY once (dishka silent last-wins; ServicesProvider docstring documents the exclusion)
- **Single process**: `pocketquant.app.main` on :41921 — full runtime + ALL API routes + SPA fallback. Single uvicorn worker only (scheduler/WS/broker are in-process singletons)
- `OrderPositionQueryService` routes (in-RAM engine state) now WORK publicly via nginx (previously 500'd in bff by design) — unauthenticated read of live orders/positions, consistent with overall no-auth API posture
- Known wart: tracked_symbols router mounted twice (via market_data.py aggregator AND directly with prefix="/market-data") → 5 duplicate entries in route_inventory snapshot; identical handlers, pre-existing from bff

### Layer Structure (post 4-subpackage collapse, 2026-06-11)
Single package `pocketquant` at root `src/` (PEP 420 namespace). `trading` dissolved (services → engine, OKX → core/infra/brokers/okx, webhooks deleted); `bff` merged into `app`.
```
src/pocketquant/
  core/      # 0 internal deps — domain, infra (persistence, brokers/{paper,okx}, binance, scheduling), common, config
  engine/    # -> core — strategy/order/position/risk app services + market_data services + strategy_command/query + orders_positions services
  backtest/  # -> core, engine
  app/       # -> all — single backend: routes/, di/, middleware/, common/, runtime (scheduler, WS feed, reconcile, backtest worker)
web/       # Node SPA at repo root
```
- import-linter: 7 contracts, layers `core ◁ engine ◁ backtest ◁ app`
- Tests: `tests/{core,engine,backtest,app}_test` + `tests/baseline` (openapi_app_snapshot, route_inventory_app_snapshot, layout contract with negative assertions for trading/bff); root `tests/conftest.py` = env seeding + prod-DB guard
- Baseline snapshots regenerate via `just baseline` (BASELINE_UPDATE=1); test_single_entrypoint_routes.py duplicates test_route_inventory.py signal (same snapshot, no independent check)
- `tests/app_test/unit/handlers/sync/conftest.py`: autouse fixture rebinds module loggers (structlog cache_logger_on_first_use makes capture_logs order-dependent otherwise)
- APScheduler MongoDBJobStore (`apscheduler_jobs` collection) persists pickled text func refs `pocketquant.engine.market_data.app_services.sync_jobs:<fn>`; apscheduler 3.11 `_get_jobs` auto-deletes unrestorable jobs, `replace_existing=True` update_job rewrites job_state — module renames self-heal at boot (verified from installed source 2026-06-10)

### ID Convention (Phase 1+3 done 2026-06-12, uuid7-id-centralization plan)
- Phase 3: `migrate_job_history_uuid_ids` boot migration re-keys legacy ObjectId `_id` → uuid7 str. Boot migration precedent now: tracked_symbols (delete-then-insert, log-before-delete) + job_history (copy-then-delete w/ `_migrated_from` crash marker; delete-then-insert only for listener docs under unique partial idx_skip_idempotency). `_migrated_from` stays on docs permanently — `_serialize` whitelist hides it from API
- `bson` import banned via ruff TID251 (pyproject.toml:59-61); the only sanctioned `noqa: TID251` is the migration test that fabricates legacy ObjectId shape
- PK attributes are `UUID` in RAM (`generate_id()` = uuid7), `str` in Mongo `_id` (to_mongo `str()`, from_mongo `UUID()`); Bar is the precedent pattern
- Flipped: OrderAggregate.id, PositionAggregate.id, Fill.fill_id, backtest Order.order_id, Trade.trade_id, OptimizationResult.id
- Still str (deferred): BacktestRequest.id (P4), BacktestResult.id (P5, `save_for_subscription` overrides id=sub_id 16-hex), Subscription.id (P6, sha256 16-hex)
- FK reference fields stay str by decision: subscription_id, run_id, Fill.order_id, entry/exit_order_id, resulting_trade_id, broker_order_id, backtest_id
- Boundary rule: dict keys (paper_broker._orders/_pending_orders/_order_events, order_app_service._orders/_pending/_broker_map, result_collector._orders_by_id), OrderResult.order_id, domain events, structlog kwargs all take `str(id)` — UUID-as-dict-key vs str lookup is the silent-failure class to grep on every later phase

### Tech Stack
- Python 3.14, FastAPI, Pydantic, structlog, MongoDB (pymongo native async), Redis, APScheduler
- Type checking: pyright (0 errors as of 2026-02-14)
- Linting: ruff (42 issues, 41 auto-fixable -- mostly import sorting)
- Tests: pytest + pytest-asyncio (60 tests passing)

### DI Pattern (updated 2026-06-11)
- [project_dishka_di.md](project_dishka_di.md) -- dishka providers per process, DishkaRoute gotcha, silent duplicate-provider override

### Deploy Pipeline
- [project_deploy_pipeline.md](project_deploy_pipeline.md) -- develop push = prod deploy (no staging); verify never probes /api; rollback = IMAGE_TAG re-deploy

### Review Reports
- `plans/reports/code-review-260214-persistence-layer.md` - Persistence layer extraction review
- `plans/reports/code-review-260214-clean-architecture-refactor.md` - Full clean arch refactor review
- `plans/reports/code-reviewer-260214-1331-mediator-auto-discovery.md` - Mediator decorator review
- `plans/reports/code-reviewer-260213-0127-vertical-slice-review.md` - Vertical slice review
- `plans/reports/code-reviewer-260215-1908-database-layer-review.md` - Database layer deep dive (12 categories)
- `plans/reports/code-review-260313-1243-dishka-migration.md` - Dishka DI migration review (critical DishkaRoute bug)
- `plans/reports/code-reviewer-260315-1740-ddd-folder-restructure.md` - DDD folder restructure review (1 critical: broken to_dict)
