---
phase: 2
title: "Backtest Package Extraction"
status: pending
priority: P1
effort: 4h
---

# Phase 2: Backtest Package Extraction

## Overview

Extract backtesting engine into `pocketquant-backtest`. Lowest risk phase — backtest has zero coupling to trading (confirmed by scout + import-linter).

## Package Structure

```
packages/pocketquant-backtest/
├── pyproject.toml
└── src/pocketquant/backtest/
    ├── __init__.py
    ├── domain/
    │   ├── __init__.py
    │   ├── entities.py          ← src/domain/backtest/entities.py
    │   ├── value_objects.py     ← src/domain/backtest/value_objects.py
    │   └── services/
    │       ├── __init__.py
    │       └── performance_calculator.py  ← src/domain/backtest/services/
    ├── engine/
    │   ├── __init__.py
    │   ├── backtest_app_service.py        ← src/application/backtesting/backtest_app_service.py
    │   ├── historical_replay_app_service.py  ← src/application/backtesting/historical_replay_app_service.py
    │   └── result_collector.py            ← src/application/backtesting/result_collector.py
    ├── optimization/
    │   ├── __init__.py
    │   ├── grid_optimization_app_service.py  ← src/application/backtesting/grid_optimization_app_service.py
    │   └── models/
    │       ├── __init__.py
    │       ├── backtest_config.py    ← src/application/backtesting/models/backtest_config.py
    │       └── optimization_config.py  ← src/application/backtesting/models/optimization_config.py
    └── handlers/
        ├── __init__.py
        ├── router.py              ← src/features/backtesting/router.py
        ├── run/                   ← src/features/backtesting/run/
        ├── optimize/              ← src/features/backtesting/optimize/
        ├── get_result/            ← src/features/backtesting/get_result/
        ├── get_optimization/      ← src/features/backtesting/get_optimization/
        └── list_results/          ← src/features/backtesting/list_results/
```

## pyproject.toml

```toml
[project]
name = "pocketquant-backtest"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
    "pocketquant-core",
    "numpy>=1.26.0",
    "pandas>=2.1.0",
]

[tool.uv.sources]
pocketquant-core = { workspace = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/pocketquant"]
```

## Import Remapping

| Old | New |
|-----|-----|
| `from src.domain.backtest` | `from pocketquant.backtest.domain` |
| `from src.application.backtesting` | `from pocketquant.backtest.engine` or `pocketquant.backtest.optimization` |
| `from src.features.backtesting` | `from pocketquant.backtest.handlers` |
| `from src.domain.bar` | `from pocketquant.core.domain.bar` |
| `from src.domain.order` | `from pocketquant.core.domain.order` |
| `from src.common.*` | `from pocketquant.core.common.*` |
| `from src.persistence.*` | `from pocketquant.core.persistence.*` |
| `from src.infrastructure.brokers.paper` | `from pocketquant.core.infrastructure.brokers.paper` |

## Steps

### 2.1 Create package skeleton + pyproject.toml
### 2.2 Move domain/backtest/ files (git mv)
### 2.3 Move application/backtesting/ files into engine/ and optimization/
### 2.4 Move features/backtesting/ into handlers/
### 2.5 Update all imports in moved files
### 2.6 Update remaining src/ files that imported from backtest modules
### 2.7 Validate

```bash
uv sync --package pocketquant-backtest
uv run --package pocketquant-backtest python -c "from pocketquant.backtest.domain.entities import BacktestResult; print('OK')"
uv run --package pocketquant-backtest pyright packages/pocketquant-backtest/
```

## Todo

- [ ] Create package skeleton
- [ ] Move domain files
- [ ] Move engine files
- [ ] Move optimization files
- [ ] Move handler files
- [ ] Update imports in backtest package
- [ ] Update imports in remaining src/ that reference backtest
- [ ] `uv sync --package pocketquant-backtest`
- [ ] Pyright passes
- [ ] Commit

## Success Criteria

- `uv sync --package pocketquant-backtest` succeeds without trading installed
- Backtest package imports only from `pocketquant.core.*` — zero imports from trading/api
- Pyright 0 errors
