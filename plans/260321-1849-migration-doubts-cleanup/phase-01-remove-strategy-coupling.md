# Phase 1: Remove StrategyAppService Dead Coupling from Backtest

## Overview
- **Priority:** P0
- **Status:** completed
- **Risk:** Zero — dead parameter removal, no behavioral change

`strategy_app_service` is injected into BacktestAppService and GridOptimizationAppService but never called. Pure DI wiring debt.

## Files to Modify

### 1. `packages/pocketquant-backtest/src/pocketquant/backtest/engine/backtest_app_service.py`
- Remove lines 23-24 (`if TYPE_CHECKING: from ... import StrategyAppService`)
- Remove `strategy_app_service: StrategyAppService` from `__init__` param (line 49)
- Remove `self._strategy_app_service = strategy_app_service` (line 56)
- Remove `TYPE_CHECKING` from typing import if no other uses

### 2. `packages/pocketquant-backtest/src/pocketquant/backtest/optimization/grid_optimization_app_service.py`
- Remove lines 24-25 (`if TYPE_CHECKING: from ... import StrategyAppService`)
- Remove `strategy_app_service: StrategyAppService` from `__init__` param (line 50)
- Remove `self._strategy_app_service = strategy_app_service` (line 55)
- Remove `TYPE_CHECKING` from typing import if no other uses

### 3. `packages/pocketquant-backtest/src/pocketquant/backtest/handlers/run/handler.py`
- Remove line 7 (`from pocketquant.trading... import StrategyAppService`)
- Remove `strategy_app_service: StrategyAppService` from `__init__` param (line 23)
- Remove `self._strategy_app_service = strategy_app_service` (line 28)
- Remove `strategy_app_service=self._strategy_app_service` from BacktestAppService constructor (line 55)

### 4. `packages/pocketquant-backtest/src/pocketquant/backtest/handlers/optimize/handler.py`
- Remove line 7 (`from pocketquant.trading... import StrategyAppService`)
- Remove `strategy_app_service: StrategyAppService` from `__init__` param (line 23)
- Remove `self._strategy_app_service = strategy_app_service` (line 29)
- Remove `strategy_app_service=self._strategy_app_service` from GridOptimizationAppService constructor (line 52)

### 5. `pyproject.toml` (root)
- Remove all 4 entries from `ignore_imports` in the "Backtest depends only on Core" contract (lines 58-63)
- Remove the `ignore_imports` key entirely since it becomes empty

## Verification
```bash
uv run lint-imports
```
Should pass with zero violations and zero ignored imports.

## Todo
- [x] Remove StrategyAppService from backtest_app_service.py
- [x] Remove StrategyAppService from grid_optimization_app_service.py
- [x] Remove StrategyAppService from run/handler.py
- [x] Remove StrategyAppService from optimize/handler.py
- [x] Remove ignore_imports from pyproject.toml
- [x] Run lint-imports — verify clean
