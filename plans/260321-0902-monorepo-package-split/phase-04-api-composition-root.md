---
phase: 4
title: "API Package — Composition Root"
status: pending
priority: P1
effort: 4h
---

# Phase 4: API Package — Composition Root

## Overview

Everything remaining in `src/` becomes `pocketquant-api`. This is the composition root — it wires all packages together via Dishka DI, hosts FastAPI routes, and provides the concrete `BrokerFactory`.

## Package Structure

```
packages/pocketquant-api/
├── pyproject.toml
└── src/pocketquant/api/
    ├── __init__.py
    ├── main.py                    ← src/main.py
    ├── main_extensions.py         ← src/main_extensions.py
    ├── market_data/
    │   ├── __init__.py
    │   ├── app_services/
    │   │   ├── __init__.py
    │   │   ├── bar_app_service.py      ← src/application/market_data/bar_app_service.py
    │   │   ├── quote_app_service.py    ← src/application/market_data/quote_app_service.py
    │   │   ├── quote_dto.py            ← src/application/market_data/quote_dto.py
    │   │   └── sync_jobs.py            ← src/application/market_data/sync_jobs.py
    │   └── handlers/                   ← src/features/market_data/ (all sub-handlers)
    │       ├── __init__.py
    │       ├── router.py
    │       ├── list_symbols/
    │       ├── ohlcv/
    │       ├── quotes/
    │       ├── status/
    │       └── sync/
    ├── di/
    │   ├── __init__.py            ← src/di/__init__.py
    │   ├── core.py                ← src/di/core.py
    │   ├── persistence.py         ← src/di/persistence.py
    │   ├── infrastructure.py      ← src/di/infrastructure.py
    │   ├── market_data.py         ← src/di/market_data.py
    │   ├── trading.py             ← src/di/trading.py
    │   ├── handlers.py            ← src/di/handlers.py
    │   ├── container.py           ← src/container.py
    │   └── broker_factory.py      ← src/infrastructure/brokers/factory.py (NEW LOCATION)
    └── middleware/
        ├── __init__.py
        (any web-specific middleware extracted from main_extensions)
```

## pyproject.toml

```toml
[project]
name = "pocketquant-api"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
    "pocketquant-core",
    "pocketquant-backtest",
    "pocketquant-trading",
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "dishka>=1.9.1",
]

[tool.uv.sources]
pocketquant-core = { workspace = true }
pocketquant-backtest = { workspace = true }
pocketquant-trading = { workspace = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/pocketquant"]

[project.scripts]
pocketquant = "pocketquant.api.main:run"
```

## Concrete BrokerFactory

Move `src/infrastructure/brokers/factory.py` to api, update imports:

```python
# packages/pocketquant-api/src/pocketquant/api/di/broker_factory.py
from pocketquant.core.infrastructure.brokers.interface import IBroker, IBrokerFactory
from pocketquant.core.infrastructure.brokers.paper import PaperBroker
from pocketquant.trading.brokers.okx import OKXBroker

class BrokerFactory(IBrokerFactory):
    """Concrete factory — composition root knows all implementations."""

    def create(self, broker_type: str, config: dict) -> IBroker:
        if broker_type == "paper":
            return PaperBroker(...)
        elif broker_type == "okx":
            return OKXBroker(...)
        raise ValueError(f"Unknown broker type: {broker_type}")
```

## DI Provider Updates

Each provider updates imports to reference correct packages:

```python
# di/core.py
from pocketquant.core.config import Settings, get_settings
from pocketquant.core.common.mediator import Mediator
from pocketquant.core.common.messaging import EventBus

# di/trading.py
from pocketquant.trading.app_services import OrderAppService, PositionAppService, StrategyAppService
from pocketquant.api.di.broker_factory import BrokerFactory

# di/handlers.py
from pocketquant.backtest.handlers import ...  # backtest handlers
from pocketquant.trading.handlers import ...   # trading handlers
from pocketquant.api.market_data.handlers import ...  # market data handlers
```

## Import Remapping

| Old | New |
|-----|-----|
| `from src.main` | `from pocketquant.api.main` |
| `from src.container` | `from pocketquant.api.di.container` |
| `from src.di` | `from pocketquant.api.di` |
| `from src.application.market_data` | `from pocketquant.api.market_data.app_services` |
| `from src.features.market_data` | `from pocketquant.api.market_data.handlers` |

## Steps

### 4.1 Create package skeleton + pyproject.toml
### 4.2 Move market_data app services + handlers
### 4.3 Move DI providers + container
### 4.4 Move main.py + main_extensions.py
### 4.5 Move BrokerFactory, refactor to use IBrokerFactory
### 4.6 Update all DI provider imports to reference correct packages
### 4.7 Delete old src/ directory (should be empty)
### 4.8 Validate

```bash
uv sync --package pocketquant-api
uv run --package pocketquant-api python -c "from pocketquant.api.main import create_app; print('OK')"
uv run --package pocketquant-api uvicorn pocketquant.api.main:create_app --factory --host 0.0.0.0 --port 8765
```

## Todo

- [ ] Create package skeleton
- [ ] Move market_data files
- [ ] Move DI files
- [ ] Move main entry files
- [ ] Refactor BrokerFactory to concrete impl of IBrokerFactory
- [ ] Update all DI imports across packages
- [ ] Delete old empty src/ directory
- [ ] `uv sync --package pocketquant-api`
- [ ] Server starts successfully
- [ ] Pyright passes
- [ ] Commit

## Success Criteria

- `uv run --package pocketquant-api uvicorn ...` starts and serves all routes
- All health check endpoints respond
- DI container resolves all 27 handlers
- Old `src/` directory is empty/deleted
