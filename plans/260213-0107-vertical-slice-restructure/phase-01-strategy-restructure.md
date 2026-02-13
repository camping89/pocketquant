# Phase 1: Strategy Restructure

## Priority: High | Effort: Low | Risk: Low

Smallest feature, proves the pattern. 5 operations + 4 infra folders to consolidate.

## Context

- [Plan](plan.md)
- [Brainstorm](../reports/brainstorm-260213-0107-vertical-slice-restructure.md)

## Current → Target

```
strategy/                          strategy/
├── api/                           ├── router.py
│   ├── __init__.py                ├── base/
│   └── routes.py                  │   ├── __init__.py
├── base/                          │   ├── strategy_config.py
│   ├── __init__.py                │   ├── strategy_interface.py
│   ├── strategy_config.py         │   ├── strategy_engine.py
│   └── strategy_interface.py      │   ├── yaml_loader.py
├── engine/                        │   ├── ma_crossover.py
│   ├── __init__.py                │   └── registry/  (if exists)
│   └── strategy_engine.py         ├── get_all/
├── examples/                      │   ├── __init__.py
│   ├── __init__.py                │   ├── query.py
│   └── ma_crossover.py            │   ├── handler.py
├── handlers/                      │   └── route.py
│   ├── __init__.py                ├── get_one/
│   ├── get_all/                   ├── load/
│   ├── get_one/                   ├── start/
│   ├── load/                      └── stop/
│   ├── start/
│   └── stop/
├── loader/
│   ├── __init__.py
│   └── yaml_loader.py
├── registry/
└── __init__.py
```

## Files to Modify

**Move (git mv):**
- `engine/strategy_engine.py` → `base/strategy_engine.py`
- `loader/yaml_loader.py` → `base/yaml_loader.py`
- `examples/ma_crossover.py` → `base/ma_crossover.py`
- `handlers/get_all/` → `get_all/`
- `handlers/get_one/` → `get_one/`
- `handlers/load/` → `load/`
- `handlers/start/` → `start/`
- `handlers/stop/` → `stop/`

**Create:**
- `router.py` — content from `api/routes.py`, updated imports

**Delete (after moves):**
- `api/` folder (routes.py, __init__.py)
- `engine/` folder (empty after move)
- `loader/` folder (empty after move)
- `examples/` folder (empty after move)
- `handlers/` folder (empty after moves)
- `handlers/__init__.py` (re-exports no longer needed)

**Update:**
- `base/__init__.py` — add engine, loader, example re-exports
- `__init__.py` — update all import paths (handlers → root, api → router)
- `router.py` — import from `src.features.strategy.get_all.route` etc.
- Each operation's internal imports (handler.py, route.py) — `handlers.X.Y` → `X.Y`
- `base/yaml_loader.py` — update import of `strategy_config`
- `base/strategy_interface.py` — import path already correct (within base/)

## Import Changes

### Internal (within strategy/)

| Old Path | New Path |
|----------|----------|
| `src.features.strategy.handlers.get_all` | `src.features.strategy.get_all` |
| `src.features.strategy.handlers.get_one` | `src.features.strategy.get_one` |
| `src.features.strategy.handlers.load` | `src.features.strategy.load` |
| `src.features.strategy.handlers.start` | `src.features.strategy.start` |
| `src.features.strategy.handlers.stop` | `src.features.strategy.stop` |
| `src.features.strategy.api.routes` | `src.features.strategy.router` |
| `src.features.strategy.engine.strategy_engine` | `src.features.strategy.base.strategy_engine` |
| `src.features.strategy.loader.yaml_loader` | `src.features.strategy.base.yaml_loader` |
| `src.features.strategy.examples.ma_crossover` | `src.features.strategy.base.ma_crossover` |

### External (defer to Phase 6)

- `main.py` — imports from `src.features.strategy` (via `__init__.py` re-exports, so safe)
- `backtesting/engine/backtest_runner.py` — TYPE_CHECKING import of StrategyEngine (update path)
- `backtesting/optimizer/grid_optimizer.py` — TYPE_CHECKING import of StrategyEngine (update path)

## Implementation Steps

1. Create `base/strategy_engine.py` via `git mv engine/strategy_engine.py base/`
2. Create `base/yaml_loader.py` via `git mv loader/yaml_loader.py base/`
3. Create `base/ma_crossover.py` via `git mv examples/ma_crossover.py base/`
4. Move `registry/` into `base/registry/` if it exists and has content
5. Move each operation: `git mv handlers/get_all .` (repeat for get_one, load, start, stop)
6. Create `router.py` from `api/routes.py` content with updated imports
7. Update imports in each operation's files (handler.py, route.py, __init__.py)
8. Update `base/__init__.py` — re-export StrategyEngine, StrategyLoader, MACrossoverStrategy
9. Update `strategy/__init__.py` — point to new paths
10. Delete empty folders: `api/`, `engine/`, `loader/`, `examples/`, `handlers/`
11. Run `ruff check src/features/strategy/` + `pyright src/features/strategy/`

## Todo

- [x] Move infra files to base/
- [x] Move operations to feature root
- [x] Create router.py
- [x] Update all internal imports
- [x] Update __init__.py re-exports
- [x] Delete empty old folders
- [x] Verify ruff + pyright pass

## Implementation Status

**COMPLETED** - 2026-02-13 01:35

All tasks completed successfully. See report: `plans/reports/fullstack-developer-260213-0128-strategy-restructure.md`

### Summary
- 28 Python files restructured
- 5 operations moved to feature root
- 3 infrastructure files consolidated to base/
- Git history preserved for all moves
- Ruff: PASS (5 auto-fixes)
- Pyright: PASS (0 errors)
- Import test: PASS

## Success Criteria

- All strategy imports resolve correctly
- `ruff check` passes on strategy/
- `pyright` passes on strategy/
- Feature `__init__.py` exports unchanged (backward compat for main.py)
- `ls strategy/` shows: base/, get_all/, get_one/, load/, start/, stop/, router.py, __init__.py
