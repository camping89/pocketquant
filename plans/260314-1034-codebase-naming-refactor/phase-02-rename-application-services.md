# Phase 2: Rename Application Services to `*AppService`

**Priority:** High
**Status:** completed
**Depends on:** Phase 1 (DI folder paths)

## Overview

Rename 8 application-layer classes to use uniform `AppService` suffix. For each: rename file, rename class, update all imports.

## Rename Order (leaf-first to avoid broken intermediate states)

### Batch A -- Leaf services (no application-layer dependents)

| # | Old Class | New Class | Old File | New File |
|---|-----------|-----------|----------|----------|
| 1 | `BarManager` | `BarAppService` | `src/application/market_data/bar_manager.py` | `src/application/market_data/bar_app_service.py` |
| 2 | `HistoricalReplayEngine` | `HistoricalReplayAppService` | `src/application/backtesting/historical_replay_engine.py` | `src/application/backtesting/historical_replay_app_service.py` |
| 3 | `OrderManager` | `OrderAppService` | `src/application/trading/order_manager.py` | `src/application/trading/order_app_service.py` |
| 4 | `PositionTracker` | `PositionAppService` | `src/application/trading/position_tracker.py` | `src/application/trading/position_app_service.py` |

### Batch B -- Services that depend on Batch A

| # | Old Class | New Class | Old File | New File |
|---|-----------|-----------|----------|----------|
| 5 | `QuoteService` | `QuoteAppService` | `src/application/market_data/quote_service.py` | `src/application/market_data/quote_app_service.py` |
| 6 | `BacktestRunner` | `BacktestAppService` | `src/application/backtesting/backtest_runner.py` | `src/application/backtesting/backtest_app_service.py` |

### Batch C -- Top-level orchestrators

| # | Old Class | New Class | Old File | New File |
|---|-----------|-----------|----------|----------|
| 7 | `GridOptimizer` | `GridOptimizationAppService` | `src/application/backtesting/grid_optimizer.py` | `src/application/backtesting/grid_optimization_app_service.py` |
| 8 | `StrategyEngine` | `StrategyAppService` | `src/application/strategy/strategy_engine.py` | `src/application/strategy/strategy_app_service.py` |

## Files to Update Per Rename

### 1. BarManager -> BarAppService

**File rename:** `bar_manager.py` -> `bar_app_service.py`
**Class rename:** `BarManager` -> `BarAppService`

Files importing:
- `src/application/market_data/quote_service.py` (becomes `quote_app_service.py` in step 5)
- `src/di/market_data.py` (after Phase 1)
- `testscripts/run_sync_jobs.py`

### 2. HistoricalReplayEngine -> HistoricalReplayAppService

**File rename:** `historical_replay_engine.py` -> `historical_replay_app_service.py`
**Class rename:** `HistoricalReplayEngine` -> `HistoricalReplayAppService`

Files importing:
- `src/application/backtesting/backtest_runner.py` (becomes `backtest_app_service.py` in step 6)
- `src/features/backtesting/__init__.py`

### 3. OrderManager -> OrderAppService

**File rename:** `order_manager.py` -> `order_app_service.py`
**Class rename:** `OrderManager` -> `OrderAppService`

Files importing:
- `src/application/strategy/strategy_engine.py` (TYPE_CHECKING import, becomes `strategy_app_service.py` in step 8)
- `src/di/trading.py`
- `src/features/trading/__init__.py`
- `src/features/trading/list_orders/handler.py`
- `src/features/trading/get_order/handler.py`
- `testscripts/run_sync_jobs.py`

### 4. PositionTracker -> PositionAppService

**File rename:** `position_tracker.py` -> `position_app_service.py`
**Class rename:** `PositionTracker` -> `PositionAppService`

Files importing:
- `src/application/strategy/strategy_engine.py` (TYPE_CHECKING import, becomes `strategy_app_service.py` in step 8)
- `src/di/trading.py`
- `src/features/trading/__init__.py`
- `src/features/trading/list_positions/handler.py`
- `src/features/trading/get_position/handler.py`
- `testscripts/run_sync_jobs.py`

### 5. QuoteService -> QuoteAppService

**File rename:** `quote_service.py` -> `quote_app_service.py`
**Class rename:** `QuoteService` -> `QuoteAppService`

Files importing:
- `src/di/market_data.py`
- `src/features/market_data/quotes/get_all/handler.py`
- `src/features/market_data/quotes/get_current_bar/route.py`
- `src/features/market_data/quotes/start_feed/handler.py`
- `src/features/market_data/quotes/stop_feed/handler.py`
- `src/features/market_data/quotes/subscribe/handler.py`
- `src/features/market_data/quotes/unsubscribe/handler.py`
- `src/features/market_data/status/get_quote_service_status/handler.py`
- `testscripts/run_sync_jobs.py`

**Note:** `GetQuoteServiceStatusHandler`, `GetQuoteServiceStatusQuery`, `QuoteServiceStatus` (Pydantic response model in route) keep their names -- they describe the feature/query, not the class itself.

### 6. BacktestRunner -> BacktestAppService

**File rename:** `backtest_runner.py` -> `backtest_app_service.py`
**Class rename:** `BacktestRunner` -> `BacktestAppService`

Files importing:
- `src/application/backtesting/grid_optimizer.py` (becomes `grid_optimization_app_service.py` in step 7)
- `src/features/backtesting/__init__.py`
- `src/features/backtesting/run/handler.py`

### 7. GridOptimizer -> GridOptimizationAppService

**File rename:** `grid_optimizer.py` -> `grid_optimization_app_service.py`
**Class rename:** `GridOptimizer` -> `GridOptimizationAppService`

Files importing:
- `src/features/backtesting/__init__.py`
- `src/features/backtesting/optimize/handler.py`

### 8. StrategyEngine -> StrategyAppService

**File rename:** `strategy_engine.py` -> `strategy_app_service.py`
**Class rename:** `StrategyEngine` -> `StrategyAppService`

Files importing:
- `src/di/trading.py`
- `src/features/strategy/__init__.py`
- `src/features/strategy/get_all/handler.py`
- `src/features/strategy/get_one/handler.py`
- `src/features/strategy/load/handler.py`
- `src/features/strategy/start/handler.py`
- `src/features/strategy/stop/handler.py`
- `src/features/backtesting/run/handler.py`
- `src/features/backtesting/optimize/handler.py`
- `src/application/backtesting/backtest_runner.py` (TYPE_CHECKING, now `backtest_app_service.py`)
- `src/application/backtesting/grid_optimizer.py` (TYPE_CHECKING, now `grid_optimization_app_service.py`)
- `testscripts/run_sync_jobs.py`

Also update:
- `src/main.py` line 52 comment: `StrategyEngine.stop` -> `StrategyAppService.stop`

## __init__.py Re-exports to Update

### `src/features/backtesting/__init__.py`
- `BacktestRunner` -> `BacktestAppService` (import + `__all__`)
- `HistoricalReplayEngine` -> `HistoricalReplayAppService` (import + `__all__`)
- `GridOptimizer` -> `GridOptimizationAppService` (import + `__all__`)

### `src/features/strategy/__init__.py`
- `StrategyEngine` -> `StrategyAppService` (import + `__all__`)

### `src/features/trading/__init__.py`
- `OrderManager` -> `OrderAppService` (import + `__all__`)
- `PositionTracker` -> `PositionAppService` (import + `__all__`)

## Implementation Steps

For each rename (in order 1-8):
1. `git mv` old file to new file
2. Find-replace class name in the renamed file
3. Update all importing files (import path + class name)
4. Update `__init__.py` re-exports

After all 8:
5. Run `ruff check src/`
6. Run `pyright src/`
7. Run `pytest`

## Todo

- [x] Rename BarManager -> BarAppService (file + class + 3 importers)
- [x] Rename HistoricalReplayEngine -> HistoricalReplayAppService (file + class + 2 importers)
- [x] Rename OrderManager -> OrderAppService (file + class + 6 importers)
- [x] Rename PositionTracker -> PositionAppService (file + class + 6 importers)
- [x] Rename QuoteService -> QuoteAppService (file + class + 9 importers)
- [x] Rename BacktestRunner -> BacktestAppService (file + class + 3 importers)
- [x] Rename GridOptimizer -> GridOptimizationAppService (file + class + 2 importers)
- [x] Rename StrategyEngine -> StrategyAppService (file + class + 12 importers)
- [x] Update `src/features/backtesting/__init__.py` re-exports
- [x] Update `src/features/strategy/__init__.py` re-exports
- [x] Update `src/features/trading/__init__.py` re-exports
- [x] Update `src/main.py` comment on line 52
- [x] Run lint + typecheck + tests

## Success Criteria

- No references to old class names in `src/` (except docstrings describing migration)
- All `__init__.py` re-exports use new names
- DI providers resolve new class names
- All tests pass
