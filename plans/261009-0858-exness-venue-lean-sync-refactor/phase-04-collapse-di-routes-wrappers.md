---
phase: 4
title: "Collapse DI, routes and scalar wrappers"
status: pending
priority: P1
effort: 3d
dependencies: [3]
---

# Phase 04: Collapse DI, routes and scalar wrappers

## Context Links
- Advice §2.3. Keep the ports, aggregates, PaperBroker/live symmetry and 3 import-linter contracts.
- DI today is 11 files and 493 LOC: `src/pocketquant/app/di/{__init__,backtest_worker,broker_factory,container,core,execution,infrastructure,market_data,persistence,services,trading_services}.py`. `services.py:6-9` warns that the last duplicate registration silently wins. After Phase 03, `infrastructure.py` holds `get_sync_policies` (the `SyncPolicies` registry with the Binance policy) and no module provides `IDataProvider` or `IRealtimeQuoteProvider` directly.
- Market-data routes today: `src/pocketquant/app/routes/{market_data,market_data_ohlcv,market_data_status,market_data_sync,integrity,list_symbols,tracked_symbols}.py` plus `market_data_quotes.py`. They are mounted in `src/pocketquant/app/main_extensions.py:366-406` (`register_routes`).
- Scalar wrapper services:
  - `backtest/backtest_query_service.py:51`, `backtest/backtest_command_service.py:74`
  - `engine/market_data/quotes_service.py:54`, `symbols_service.py:14`, `sync_status_service.py:96,135`, `tracked_symbols_service.py:78,91,102`
  - `engine/orders_positions_service.py:50,67,86,92`
  - `engine/strategy_command_service.py:73,83,131,140`
  - `engine/strategy_query_service.py:56,59,71,101,117`
- import-linter contracts: `pyproject.toml` `[[tool.importlinter.contracts]]` (7 entries). bson is also banned by ruff `[tool.ruff.lint.flake8-tidy-imports.banned-api]`.

## Goal
`app/di` holds 3 provider modules, with strict validation and no silent duplicates. Market-data routes live in 2 files. Query/Command classes that wrap 0–2 scalars are gone, while Pydantic models stay for real request bodies. import-linter has 3 contracts. The HTTP surface is byte-identical, which the snapshots prove.

## Files to Create or Modify
- Create: `src/pocketquant/app/di/adapters.py`
- Rewrite: `src/pocketquant/app/di/__init__.py`, `src/pocketquant/app/di/infrastructure.py`, `src/pocketquant/app/di/services.py`
- Delete: `src/pocketquant/app/di/{backtest_worker,broker_factory,container,core,execution,market_data,persistence,trading_services}.py`
- Rewrite: `src/pocketquant/app/routes/market_data.py`. Delete `src/pocketquant/app/routes/{market_data_ohlcv,market_data_status,market_data_sync,integrity,list_symbols,tracked_symbols}.py`.
- Modify:
  - `src/pocketquant/app/main.py`, `src/pocketquant/app/main_extensions.py`
  - `src/pocketquant/app/routes/{backtest,strategy,trading_orders_positions,market_data_quotes}.py`
  - the wrapper-owning services listed in Context Links
  - `pyproject.toml`
- Modify tests:
  - `tests/app_test/integration/app_factory.py`, `test_app_standalone_runtime.py`, `test_reconcile_di_resolution.py`, `test_di_resolution_characterization.py`
  - `tests/app_test/unit/di/test_di_data_provider.py`
  - `tests/engine_test/test_reconcile_restart_resume_integration.py`
  - `tests/engine_test/market_data/test_quotes_service.py`, `tests/engine_test/market_data/test_tracked_symbols_service.py`
  - `tests/engine_test/test_strategy_handlers_declarative.py`, `tests/engine_test/test_strategy_service.py`, `tests/engine_test/test_orders_positions_service.py`, `tests/engine_test/test_strategy_position_and_trade_handlers.py`
  - `tests/app_test/unit/handlers/status/test_get_sync_status.py`, `tests/app_test/unit/handlers/status/test_get_symbol_sync_status.py`

## Tasks

### T4.1 Branch
- **Goal:** Isolate the work.
- **Target files and symbols:** git
- **Steps:**
  1. `git switch master && git pull --ff-only && git switch -c refactor/lean-wiring`
- **Success criteria:** On the branch.
- **Verify:** `git branch --show-current` prints `refactor/lean-wiring`.

<!-- Updated: Validation Session 1 - adapters provider owns the policy registry, no standalone provider factories -->
### T4.2 DI collapsed to three provider modules
- **Goal:** Three providers (infrastructure, adapters, services), with `Settings` from context and strict validation.
- **Target files and symbols:** `app/di/infrastructure.py` → `InfrastructureProvider`, `app/di/adapters.py` → `BrokerFactory` and `AdaptersProvider`, `app/di/services.py` → `ServicesProvider`, and `app/di/__init__.py` → `create_container(settings: Settings | None = None) -> AsyncContainer`.
- **Steps:**
  1. Check that dishka supports strict validation: `uv run python -c "from dishka import STRICT_VALIDATION, from_context; print('ok')"` must print `ok`.
  2. `infrastructure.py`, `InfrastructureProvider(Provider)`:
     - `settings = from_context(provides=Settings, scope=Scope.APP)`
     - `get_event_bus` returning `EventBus(max_history=100)`
     - the `get_database` and `get_cache` generator factories, the 11 repository `provide(...)` lines, the `get_job_scheduler` generator and `get_health_coordinator`, all copied verbatim from `persistence.py`, `infrastructure.py` and `core.py` (everything in `infrastructure.py` except `get_sync_policies` and `broker_factory`, which move to `adapters.py`)
  3. `adapters.py`: move `class BrokerFactory` verbatim from `broker_factory.py`. Then define `AdaptersProvider(Provider)` with `broker_factory = provide(BrokerFactory, scope=Scope.APP)` and `get_sync_policies(self, settings) -> SyncPolicies`, moved verbatim from `infrastructure.py` (it builds the adapters, so it belongs here).
  4. `services.py`, `ServicesProvider(Provider)`: copy every remaining factory and `provide(...)` line verbatim from `market_data.py`, `execution.py`, `trading_services.py`, `backtest_worker.py` and the current `services.py`. Do not change any factory body. Remove the duplicate-registration comment.
  5. `__init__.py`: export the three providers and `BrokerFactory`, and define `create_container(settings=None)` returning `make_async_container(InfrastructureProvider(), AdaptersProvider(), ServicesProvider(), context={Settings: settings or get_settings()}, validation_settings=STRICT_VALIDATION)`.
  6. Delete `backtest_worker.py`, `broker_factory.py`, `container.py`, `core.py`, `execution.py`, `market_data.py`, `persistence.py` and `trading_services.py`.
  7. `app/main.py`: `from pocketquant.app.di import create_container`.
  8. Tests:
     - In `app_factory.py`, delete `TestCoreProvider`. `make_test_app` and `build_test_container` use `create_container(settings)`.
     - `test_app_standalone_runtime.py` and `test_reconcile_di_resolution.py` build their containers with `create_container(settings)`.
     - `test_di_data_provider.py` uses `AdaptersProvider().get_sync_policies(mock_settings)` in place of `InfrastructureProvider().get_sync_policies(mock_settings)`; the assertions stay.
     - `test_reconcile_restart_resume_integration.py` imports `BrokerFactory` from `pocketquant.app.di.adapters`.
- **Success criteria:** Exactly 3 provider modules exist, and the DI characterization test passes unchanged except for the container builder.
- **Verify:**
  - `ls src/pocketquant/app/di/*.py | xargs -n1 basename | sort | tr '\n' ' '` prints `__init__.py adapters.py infrastructure.py services.py `.
  - `.venv/Scripts/python.exe -m pytest tests/app_test/integration tests/app_test/unit/di tests/engine_test/test_reconcile_restart_resume_integration.py tests/baseline/test_app_boot_smoke.py -q` exits 0 with `passed`.

<!-- Updated: Validation Session 3 - stale tracked_symbols comment removed during the move -->
### T4.3 Market-data routes in two files
- **Goal:** Every `/market-data/*` endpoint lives in `routes/market_data.py`. `routes/market_data_quotes.py` keeps `/quotes/*`.
- **Target files and symbols:** `src/pocketquant/app/routes/market_data.py` → `router` (`APIRouter(prefix="/market-data", tags=["Market Data"], route_class=DishkaRoute)`) and `tracked_symbols_router` (`APIRouter(tags=["Tracked Symbols"], route_class=DishkaRoute)`).
- **Steps:**
  1. Move these route functions verbatim, keeping decorator paths, `response_model`, `status_code`, `dependencies`, signatures and docstrings: `sync_symbol`, `sync_symbol_background`, `sync_bulk`, `get_sync_statuses`, `get_symbol_sync_status`, `integrity_check`, `integrity_repair`, `list_symbols`, `get_ohlcv`, `stream_bars` and their module helpers. Attach them to `router`. Move `IntegrityRequest` verbatim.
  2. Move `list_tracked_symbols`, `add_tracked_symbol`, `update_tracked_symbol`, `remove_tracked_symbol` and `backfill_tracked_symbol` verbatim onto `tracked_symbols_router`.
  3. In `sync_symbol_background`, replace the nested `run_sync` closure with `background_tasks.add_task(sync_service.sync_one, cmd)`.
  4. In `main_extensions.register_routes`, import `router as market_data_router, tracked_symbols_router` from `pocketquant.app.routes.market_data`, delete the `tracked_symbols` import, and keep `api.include_router(tracked_symbols_router, prefix="/market-data")`. Do not carry over the trailing three-line comment at the end of the current `routes/market_data.py` (`# tracked_symbols router is mounted directly in main_extensions.register_routes ...`); the new file defines `tracked_symbols_router` itself, so the comment is stale.
  5. Delete `market_data_ohlcv.py`, `market_data_status.py`, `market_data_sync.py`, `integrity.py`, `list_symbols.py` and `tracked_symbols.py`.
- **Success criteria:** The OpenAPI and route inventory snapshots are unchanged.
- **Verify:**
  - `ls src/pocketquant/app/routes/market_data*.py | wc -l` prints `2`.
  - `ls src/pocketquant/app/routes/ | grep -cE "^(integrity|list_symbols|tracked_symbols)\.py$"` prints `0`.
  - `.venv/Scripts/python.exe -m pytest tests/baseline -q` exits 0. Never set `BASELINE_UPDATE` in this phase.

### T4.4 Drop scalar Query/Command wrappers
- **Goal:** Routes pass scalars straight to services. The 22 wrapper classes are gone, and the request-body models stay.
- **Target files and symbols:** these new signatures. In each body, replace `query.x`, `cmd.x` and `request.x` with the parameter.
  - `BacktestQueryService.get_result(run_id: str)` and `BacktestCommandService.set_verdict(run_id: str, verdict: str | None)`
  - `QuoteQueryService.get_latest(symbol: str)` and `SymbolQueryService.list_symbols()`
  - `SyncStatusQueryService.get_sync_status()` and `get_symbol_sync_status(symbol: str, interval: str = "1d")`
  - `TrackedSymbolService.update(symbol: str)`, `remove(symbol: str)` and `list_all()`
  - `OrderPositionQueryService.get_order(order_id: str)`, `list_orders()`, `get_position(strategy_id: str)` and `list_positions()`
  - `StrategyCommandService.start(subscription_id: str)`, `stop(subscription_id: str)`, `remove_symbol(sub_id: str)` and `delete_strategy(strategy_id: str)`
  - `StrategyQueryService.get_all()`, `get_one(strategy_code: str)`, `list_symbols(strategy_code: str | None = None)`, `get_positions(subscription_id: str)` and `get_trades(subscription_id: str, limit: int = 100)`
- **Steps:**
  1. Delete these classes:
     - `GetBacktestQuery`, `SetVerdictCommand`, `GetLatestQuoteQuery`
     - `ListSymbolsQuery` (in both `symbols_service.py` and `strategy_query_service.py`)
     - `GetSyncStatusQuery`, `GetSymbolSyncStatusQuery`
     - `UpdateTrackedSymbolCommand`, `RemoveTrackedSymbolCommand`, `ListTrackedSymbolsQuery`
     - `GetOrderQuery`, `ListOrdersQuery`, `GetPositionQuery`, `ListPositionsQuery`
     - `StartStrategyCommand`, `StopStrategyCommand`, `RemoveSymbolCommand`, `DeleteStrategyCommand`
     - `GetStrategiesQuery`, `GetStrategyQuery`, `GetStrategyPositionsQuery`, `GetStrategyTradesQuery`
  2. Keep `RunBacktestCommand`, `ListBacktestsQuery`, `ListTradesQuery`, `GetOHLCVQuery`, `SyncSymbolCommand`, `BulkSyncCommand`, `BackfillTrackedSymbolCommand`, `AddTrackedSymbolCommand`, `AddSymbolCommand`, `CreateSubscriptionBody`, `SetVerdictBody` and `IntegrityRequest`.
  3. Update every route call site in `routes/backtest.py`, `routes/strategy.py`, `routes/trading_orders_positions.py`, `routes/market_data.py` and `routes/market_data_quotes.py`.
  4. Update the test call sites in the test files listed under "Files to Create or Modify". Change only the call shape; assertions stay unchanged.
- **Success criteria:** No wrapper class remains, pyright is clean, and the snapshots are unchanged.
- **Verify:**
  - `grep -rnwE "GetBacktestQuery|SetVerdictCommand|GetLatestQuoteQuery|ListSymbolsQuery|GetSyncStatusQuery|GetSymbolSyncStatusQuery|UpdateTrackedSymbolCommand|RemoveTrackedSymbolCommand|ListTrackedSymbolsQuery|GetOrderQuery|ListOrdersQuery|GetPositionQuery|ListPositionsQuery|StartStrategyCommand|StopStrategyCommand|RemoveSymbolCommand|DeleteStrategyCommand|GetStrategiesQuery|GetStrategyQuery|GetStrategyPositionsQuery|GetStrategyTradesQuery" src tests | wc -l` prints `0`.
  - `uv run pyright` reports `0 errors`.
  - `.venv/Scripts/python.exe -m pytest tests/baseline tests/engine_test tests/app_test -q` exits 0.

### T4.5 import-linter reduced to 3 contracts
- **Goal:** Keep only the contracts that matter: layers, core domain free of infra, and fastapi only in app.
- **Target files and symbols:** `pyproject.toml` `[[tool.importlinter.contracts]]`
- **Steps:**
  1. Keep "Layered architecture — app top tier", "Core domain stays free of infra adapters" and "fastapi only in app", with its comment.
  2. Delete "Core imports no inner package", "Engine imports no sibling/upper package" and "Backtest imports no upper package", which the layers contract already implies. Delete "No bson/ObjectId usage — UUID7 only", since ruff `banned-api` enforces it.
- **Success criteria:** 3 contracts, all kept, and the bson ban is still enforced.
- **Verify:** `uv run lint-imports` exits 0 and contains `Contracts: 3 kept, 0 broken.`. `grep -c '"bson"' pyproject.toml` prints a number ≥ 1 (the ruff banned-api entry).

<!-- Updated: Validation Session 1 - venue command reference renumbered -->
### T4.6 Phase gate
- **Goal:** Full green.
- **Target files and symbols:** whole repo
- **Steps:**
  1. `just test 2>&1 | tail -n 3`
  2. `uv run ruff check`
  3. `uv run pyright`
  4. `uv run lint-imports`
  5. The venue command from Phase 02 T2.6.
- **Success criteria:** Green, with an unchanged venue count.
- **Verify:**
  - Step 1 exits 0 with `passed` and no `failed`.
  - Step 2 prints `All checks passed!`.
  - Step 3 reports `0 errors`.
  - Step 4 shows `Contracts: 3 kept, 0 broken.`.
  - Step 5's `passed` count equals the baseline `venue:` count.

<!-- Updated: Validation Session 1 - CI verdict asserts 0 failures -->
### T4.7 Ship
- **Goal:** Deployed.
- **Target files and symbols:** git
- **Steps:**
  1. `git add -A src tests pyproject.toml plans/261009-0858-exness-venue-lean-sync-refactor`
  2. `git commit -m "refactor(app): collapse di to three providers, merge market-data routes, drop scalar query wrappers"`
  3. Ask the user for approval, then merge, push and watch CI as in Phase 01 T1.7 steps 4-6.
  4. Smoke test, expecting HTTP 200:
     ```bash
     ssh -i "$KEY" "$HOST" 'docker exec -i pocketquant-app sh -s' <<'EOF'
     curl -s -o /dev/null -w "%{http_code}" http://localhost:41921/api/v1/market-data/tracked-symbols
     EOF
     ```
- **Success criteria:** Prod is green.
- **Verify:** `gh run watch` exits 0, and the CI log `=== Verdict:` line contains `, 0 failures)`. The step 4 command prints `200`.

## Verification
T4.2 (DI: 3 modules plus characterization), T4.3 and T4.4 (snapshots unchanged) and T4.5 (3 contracts).

<!-- Updated: Validation Session 1 - stop-and-ask list for this phase -->
## Stop-and-ask
- A step would delete Binance or OKX code (moving `BrokerFactory` and the registry factory is a move, not a deletion).
- `STRICT_VALIDATION` reports an error that the Failure Protocol cannot explain.
- A test failure stays unexplained.

## Risks
- **STRICT_VALIDATION flags a latent duplicate or an unused provide** (M/M). That is the hazard being removed. Any error message goes to the Failure Protocol. Do not disable validation.
- **A route docstring change alters OpenAPI** (M/L). Mitigation: move function bodies verbatim, and the snapshot test blocks drift.
- **Moving the OKX construction code inside `BrokerFactory`** is a move, not a deletion. If a step would delete any Binance or OKX code, STOP and ask the user.

## Rollback
`git revert` the merge commit and push. There is no data impact.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.
