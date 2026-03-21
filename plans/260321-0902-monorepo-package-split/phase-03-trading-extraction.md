---
phase: 3
title: "Trading Package Extraction"
status: pending
priority: P1
effort: 5h
---

# Phase 3: Trading Package Extraction

## Overview

Extract live trading engine into `pocketquant-trading`. Medium risk — StrategyAppService has TYPE_CHECKING imports for OrderAppService/PositionAppService, but those are now in the same package so circularity is contained.

## Package Structure

```
packages/pocketquant-trading/
├── pyproject.toml
└── src/pocketquant/trading/
    ├── __init__.py
    ├── domain/
    │   ├── __init__.py           (re-exports from core for convenience, if needed)
    ├── app_services/
    │   ├── __init__.py
    │   ├── order_app_service.py     ← src/application/trading/order_app_service.py
    │   ├── position_app_service.py  ← src/application/trading/position_app_service.py
    │   ├── strategy_app_service.py  ← src/application/strategy/strategy_app_service.py
    │   └── yaml_strategy_loader.py  ← src/application/strategy/yaml_strategy_loader.py
    ├── brokers/
    │   ├── __init__.py
    │   └── okx/                     ← src/infrastructure/brokers/okx/
    │       ├── __init__.py
    │       ├── okx_broker.py
    │       ├── okx_mapper.py
    │       └── websocket/           ← src/infrastructure/brokers/okx/websocket/
    ├── webhooks/                    ← src/infrastructure/webhooks/
    │   ├── __init__.py
    │   ├── config.py
    │   └── dispatcher.py
    └── handlers/
        ├── __init__.py
        ├── trading/                 ← src/features/trading/
        │   ├── router.py
        │   ├── get_order/
        │   ├── get_position/
        │   ├── list_orders/
        │   └── list_positions/
        ├── strategy/                ← src/features/strategy/
        │   ├── router.py
        │   ├── get_all/
        │   ├── get_one/
        │   ├── load/
        │   ├── start/
        │   └── stop/
        └── risk/                    ← src/features/risk/
            └── check_risk/
```

## pyproject.toml

```toml
[project]
name = "pocketquant-trading"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
    "pocketquant-core",
    "python-okx>=0.4.1",
    "websockets>=12.0",
    "pyyaml>=6.0",
]

[tool.uv.sources]
pocketquant-core = { workspace = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/pocketquant"]
```

## Critical: StrategyAppService Refactoring

StrategyAppService currently imports `BrokerFactory` directly. After split:

```python
# Before (current):
from src.infrastructure.brokers import BrokerFactory, IBroker

# After:
from pocketquant.core.infrastructure.brokers.interface import IBroker, IBrokerFactory
```

StrategyAppService constructor changes:
```python
# Before:
def __init__(self, ..., broker_factory: BrokerFactory, ...):

# After:
def __init__(self, ..., broker_factory: IBrokerFactory, ...):
```

DI provides concrete `BrokerFactory` from api package.

## Import Remapping

| Old | New |
|-----|-----|
| `from src.application.trading` | `from pocketquant.trading.app_services` |
| `from src.application.strategy` | `from pocketquant.trading.app_services` |
| `from src.infrastructure.brokers.okx` | `from pocketquant.trading.brokers.okx` |
| `from src.infrastructure.brokers import BrokerFactory` | `from pocketquant.core...interface import IBrokerFactory` |
| `from src.infrastructure.webhooks` | `from pocketquant.trading.webhooks` |
| `from src.features.trading` | `from pocketquant.trading.handlers.trading` |
| `from src.features.strategy` | `from pocketquant.trading.handlers.strategy` |
| `from src.features.risk` | `from pocketquant.trading.handlers.risk` |
| `from src.domain.order` | `from pocketquant.core.domain.order` |
| `from src.domain.position` | `from pocketquant.core.domain.position` |

## Steps

### 3.1 Create package skeleton + pyproject.toml
### 3.2 Move app services (order, position, strategy)
### 3.3 Move OKX broker + websocket
### 3.4 Move webhooks
### 3.5 Move feature handlers (trading, strategy, risk)
### 3.6 Refactor StrategyAppService: BrokerFactory → IBrokerFactory
### 3.7 Update all imports
### 3.8 Validate

```bash
uv sync --package pocketquant-trading
uv run --package pocketquant-trading pyright packages/pocketquant-trading/
```

## Todo

- [ ] Create package skeleton
- [ ] Move app service files
- [ ] Move OKX broker files
- [ ] Move webhook files
- [ ] Move handler files
- [ ] Refactor StrategyAppService to use IBrokerFactory
- [ ] Update all imports
- [ ] `uv sync --package pocketquant-trading`
- [ ] Pyright passes
- [ ] Commit

## Success Criteria

- Trading package imports only from `pocketquant.core.*` — zero imports from backtest/api
- StrategyAppService uses `IBrokerFactory` protocol (core), not concrete `BrokerFactory`
- TYPE_CHECKING imports for OrderAppService/PositionAppService stay contained within trading
- Pyright 0 errors
