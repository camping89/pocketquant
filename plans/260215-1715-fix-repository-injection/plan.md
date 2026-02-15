---
status: completed
priority: critical
branch: feat/strategy-init
---

# Fix Repository Injection — Centralize All DB Access Through DI

## Problem
3 services call repository instance methods as class methods (`Repository.save()` instead of `self._repo.save()`). Will crash at runtime with `TypeError`. Container wires repositories correctly but never injects them into these services.

## Scope
- **6 files to modify** (no new files)
- All changes are constructor signature + call site replacements
- No logic changes, no new patterns

## Phase 1: Inject Repositories into Services

### 1.1 OrderManager (`src/application/trading/order_manager.py`)
- [x] Add `order_repository: OrderRepository` param to `__init__`
- [x] Store as `self._order_repo`
- [x] Replace all 10 occurrences of `OrderRepository.<method>` → `self._order_repo.<method>`
- [x] Remove `from src.persistence.repositories.order_repository import OrderRepository` (class import no longer needed)

### 1.2 PositionTracker (`src/application/trading/position_tracker.py`)
- [x] Add `position_repository: PositionRepository` param to `__init__`
- [x] Store as `self._position_repo`
- [x] Replace all 5 occurrences of `PositionRepository.<method>` → `self._position_repo.<method>`
- [x] Remove class import

### 1.3 BacktestRunner (`src/application/backtesting/backtest_runner.py`)
- [x] Add `backtest_repository: BacktestRepository` + `ohlcv_repository: OHLCVRepository` to `__init__`
- [x] Store as `self._backtest_repo` and `self._ohlcv_repo`
- [x] Replace 3 occurrences of static calls → instance calls
- [x] Remove class imports

## Phase 2: Update Callers of BacktestRunner

### 2.1 RunBacktestHandler (`src/features/backtesting/run/handler.py`)
- [x] Add `backtest_repository` + `ohlcv_repository` to `__init__`
- [x] Pass them when constructing `BacktestRunner`

### 2.2 GridOptimizer (`src/application/backtesting/grid_optimizer.py`)
- [x] Add `backtest_repository` + `ohlcv_repository` to `__init__`
- [x] Pass them when constructing `BacktestRunner`

### 2.3 RunOptimizationHandler (`src/features/backtesting/optimize/handler.py`)
- [x] Add `backtest_repository` + `ohlcv_repository` to `__init__`
- [x] Pass them when constructing `GridOptimizer`

## Phase 3: Update Container Wiring

### 3.1 Container (`src/container.py`)
- [x] Update `init_order_manager` to accept + pass `order_repository`
- [x] Update `init_position_tracker` to accept + pass `position_repository`
- [x] Update `order_manager` Resource provider to include `order_repository=order_repository`
- [x] Update `position_tracker` Resource provider to include `position_repository=position_repository`
- [x] Update `run_backtest_handler` Factory to include `backtest_repository` + `ohlcv_repository`
- [x] Update `run_optimization_handler` Factory to include `backtest_repository` + `ohlcv_repository`

## Phase 4: Verify
- [ ] Run linting/type check
- [ ] Run tests

## Files Changed
| File | Change |
|---|---|
| `src/application/trading/order_manager.py` | Add repo injection, replace 10 static calls |
| `src/application/trading/position_tracker.py` | Add repo injection, replace 5 static calls |
| `src/application/backtesting/backtest_runner.py` | Add 2 repo injections, replace 3 static calls |
| `src/application/backtesting/grid_optimizer.py` | Add 2 repo params, thread to BacktestRunner |
| `src/features/backtesting/run/handler.py` | Add 2 repo params, thread to BacktestRunner |
| `src/features/backtesting/optimize/handler.py` | Add 2 repo params, thread to GridOptimizer |
| `src/container.py` | Wire repositories into resource providers + handlers |

## Risk
- **Low** — Pure plumbing change. No logic modifications. Container already has all repos wired as singletons.
