# Phase 2: Backtesting Restructure

## Priority: High | Effort: Medium | Risk: Medium

5 operations + 5 infra folders. Uses sub-folders in base/ (10+ files).

## Context

- [Plan](plan.md) | Depends on: Phase 1 (pattern proven)

## Current → Target

```
backtesting/                       backtesting/
├── api/                           ├── router.py
│   ├── __init__.py                ├── base/
│   └── backtest_routes.py         │   ├── __init__.py
├── engine/                        │   ├── engine/
│   ├── backtest_runner.py         │   │   ├── backtest_runner.py
│   └── historical_replay_engine   │   │   └── historical_replay_engine.py
├── metrics/                       │   ├── metrics/
│   ├── performance_calculator.py  │   │   ├── performance_calculator.py
│   └── result_collector.py        │   │   └── result_collector.py
├── optimizer/                     │   ├── optimizer/
│   └── grid_optimizer.py          │   │   └── grid_optimizer.py
├── repository/                    │   ├── repository/
│   └── backtest_repository.py     │   │   └── backtest_repository.py
├── models/                        │   └── models/
│   ├── backtest_config.py         │       ├── backtest_config.py
│   ├── backtest_result.py         │       ├── backtest_result.py
│   ├── optimization_config.py     │       ├── optimization_config.py
│   └── optimization_result.py     │       └── optimization_result.py
├── handlers/                      ├── run/
│   ├── run/                       ├── get_result/
│   ├── get_result/                ├── list_results/
│   ├── list_results/              ├── optimize/
│   ├── optimize/                  └── get_optimization/
│   └── get_optimization/
└── __init__.py
```

## Files to Modify

**Move (git mv):**
- `engine/` → `base/engine/`
- `metrics/` → `base/metrics/`
- `optimizer/` → `base/optimizer/`
- `repository/` → `base/repository/`
- `models/` → `base/models/`
- `handlers/run/` → `run/`
- `handlers/get_result/` → `get_result/`
- `handlers/list_results/` → `list_results/`
- `handlers/optimize/` → `optimize/`
- `handlers/get_optimization/` → `get_optimization/`

**Create:**
- `router.py` — from `api/backtest_routes.py` content
- `base/__init__.py` — re-export key classes

**Delete:**
- `api/` folder
- `handlers/` folder (empty after moves)
- Old `__init__.py` files in emptied folders

**Update:**
- `__init__.py` — all import paths
- Each operation's internal imports
- `base/engine/backtest_runner.py` — imports from metrics, models, repository
- `base/optimizer/grid_optimizer.py` — imports from engine, models

## Import Changes

### Internal (within backtesting/)

| Old Path | New Path |
|----------|----------|
| `src.features.backtesting.handlers.run` | `src.features.backtesting.run` |
| `src.features.backtesting.handlers.get_result` | `src.features.backtesting.get_result` |
| `src.features.backtesting.handlers.list_results` | `src.features.backtesting.list_results` |
| `src.features.backtesting.handlers.optimize` | `src.features.backtesting.optimize` |
| `src.features.backtesting.handlers.get_optimization` | `src.features.backtesting.get_optimization` |
| `src.features.backtesting.api.backtest_routes` | `src.features.backtesting.router` |
| `src.features.backtesting.engine.*` | `src.features.backtesting.base.engine.*` |
| `src.features.backtesting.metrics.*` | `src.features.backtesting.base.metrics.*` |
| `src.features.backtesting.optimizer.*` | `src.features.backtesting.base.optimizer.*` |
| `src.features.backtesting.repository.*` | `src.features.backtesting.base.repository.*` |
| `src.features.backtesting.models.*` | `src.features.backtesting.base.models.*` |

### Cross-feature (update immediately, not deferred)

- `base/engine/backtest_runner.py` imports `src.features.market_data.models.ohlcv` — unchanged
- `base/engine/backtest_runner.py` TYPE_CHECKING import of `src.features.strategy.engine.strategy_engine` — update to `src.features.strategy.base.strategy_engine` (Phase 1 already done)
- `base/optimizer/grid_optimizer.py` same TYPE_CHECKING import — update

## Implementation Steps

1. Create `base/` with sub-folders: `mkdir base/engine base/metrics base/optimizer base/repository base/models`
2. `git mv` each infra folder's contents into `base/` sub-folders
3. `git mv` each operation from `handlers/X/` to root
4. Create `router.py` from `api/backtest_routes.py` with updated imports
5. Update all internal imports in base/ files (engine→base.engine, etc.)
6. Update all internal imports in operation files (handlers.X→X)
7. Update `base/__init__.py` — re-export BacktestRunner, GridOptimizer, BacktestRepository, models
8. Update `backtesting/__init__.py` — point to new paths
9. Delete empty folders: `api/`, `handlers/`, old `engine/`, `metrics/`, `optimizer/`, `repository/`, `models/`
10. Run `ruff check src/features/backtesting/` + `pyright src/features/backtesting/`

## Todo

- [x] Create base/ sub-folder structure
- [x] Move infra folders to base/
- [x] Move operations to feature root
- [x] Create router.py
- [x] Update all internal imports
- [x] Update cross-feature TYPE_CHECKING imports (strategy engine path)
- [x] Update __init__.py re-exports
- [x] Delete empty old folders
- [x] Verify ruff + pyright pass

## Success Criteria

- [x] All backtesting imports resolve correctly
- [x] `ruff check` passes (0 errors)
- [x] `pyright` passes (0 errors, 0 warnings)
- [x] `__init__.py` exports unchanged for main.py backward compat
- [x] `ls backtesting/` shows: base/, run/, get_result/, list_results/, optimize/, get_optimization/, router.py

## Implementation Status

**COMPLETED** - 2026-02-13 01:47

All tasks completed successfully. Report: `plans/reports/fullstack-developer-260213-0135-backtesting-restructure.md`
