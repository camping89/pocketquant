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

### ID Convention (uuid7-id-centralization plan COMPLETE, P6 done 2026-06-13)
- ALL PKs now uuid7: entity `id: UUID` in RAM (`generate_id()`), `str` in Mongo `_id` (to_mongo `str()`, from_mongo `UUID()`). No hash/natural/ObjectId PKs remain
- Subscription dedup moved from sha256-16hex PK to unique compound index `ix_subscriptions_dedup_triple` (strategy_code, symbol, interval) — created in BOTH migration and repo ensure_indexes; `SubscriptionAlreadyExistsError` carries the triple, not id
- Boot migration precedents: tracked_symbols (delete-then-insert) · job_history (copy-then-delete, `_migrated_from` marker) · subscriptions (map-based: `_id_migration_map` {old_id, new_id, payload}; step1 upsert map → step2 delete/insert + FK update_many → step3 verify then drop map; residue keeps map + error log, boot continues). Map residue across boots = needs-human signal. NOTE: boot migrations have no cross-process lock — safe only under single-instance deploy assumption
- Subscription FK fields (all str): orders.subscription_id, positions.subscription_id, backtest_runs.subscription_id, backtest_requests.sub_id — `_SUBSCRIPTION_FK_FIELDS` in main_extensions.py is canonical list
- `_SUB_ID_SHAPE` (strategy_reconcile_service.py) pins uuid version nibble 7 — orphan-unload skips uuid4/legacy-16hex keys (leak-until-restart by design); synthetic `{code}::bt::{sub_id}` never matches
- `bson` banned via ruff TID251; FK reference fields stay str by decision; boundary rule: dict keys / domain events / structlog kwargs take `str(id)` — UUID-as-dict-key vs str lookup is the silent-failure class

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
