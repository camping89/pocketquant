---
phase: 1
title: "uv Workspace Setup + Core Extraction"
status: pending
priority: P1
effort: 8h
---

# Phase 1: uv Workspace Setup + Core Extraction

## Overview

Scaffold uv workspace structure. Move shared domain, common, persistence, infrastructure, and config into `pocketquant-core`. This is the largest phase — most files move here.

## Key Decisions

- **order/position domain → core**: IStrategy and IBroker reference these types directly
- **PaperBroker → core**: shared by both backtest engine and paper trading mode
- **IBrokerFactory protocol → core**: StrategyAppService depends on this abstraction
- **All repositories → core**: user chose core owns persistence
- **config.py → core**: Settings needed by all packages

## Steps

### 1.1 Create workspace root pyproject.toml

Replace existing `pyproject.toml` with workspace root:

```toml
[project]
name = "pocketquant-workspace"
version = "0.1.0"
requires-python = ">=3.14"

[tool.uv.workspace]
members = ["packages/*"]

[tool.ruff]
target-version = "py314"
line-length = 100
select = ["E", "F", "I", "N", "W", "UP"]

[tool.pyright]
pythonVersion = "3.14"
typeCheckingMode = "standard"

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

### 1.2 Create pocketquant-core package

```
packages/pocketquant-core/
├── pyproject.toml
└── src/pocketquant/core/
    ├── __init__.py
    ├── config.py              ← from src/config.py
    ├── domain/
    │   ├── __init__.py
    │   ├── bar/               ← from src/domain/bar/
    │   ├── symbol/            ← from src/domain/symbol/
    │   ├── sync_status/       ← from src/domain/sync_status/
    │   ├── order/             ← from src/domain/order/
    │   ├── position/          ← from src/domain/position/
    │   └── shared/            ← from src/domain/shared/
    ├── concepts/
    │   ├── __init__.py
    │   ├── strategy/          ← from src/domain/concepts/strategy/
    │   ├── risk/              ← from src/domain/concepts/risk/
    │   └── quote/             ← from src/domain/concepts/quote/
    ├── common/                ← from src/common/
    ├── persistence/           ← from src/persistence/
    └── infrastructure/
        ├── __init__.py
        ├── tradingview/       ← from src/infrastructure/tradingview/
        ├── scheduling/        ← from src/infrastructure/scheduling/
        ├── http_client/       ← from src/infrastructure/http_client/
        └── brokers/
            ├── __init__.py
            ├── interface.py   ← from src/infrastructure/brokers/interface.py
            ├── models.py      ← from src/infrastructure/brokers/models.py
            └── paper/         ← from src/infrastructure/brokers/paper/
```

Core `pyproject.toml`:

```toml
[project]
name = "pocketquant-core"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "pymongo>=4.16.0",
    "redis>=5.0.0",
    "apscheduler>=3.10.0",
    "tvdatafeed @ git+https://github.com/rongardF/tvdatafeed.git",
    "websockets>=12.0",
    "pandas>=2.1.0",
    "numpy>=1.26.0",
    "pyyaml>=6.0",
    "structlog>=24.1.0",
    "httpx>=0.26.0",
    "rich>=13.0.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/pocketquant"]
```

### 1.3 Add IBrokerFactory protocol to core

New file: `packages/pocketquant-core/src/pocketquant/core/infrastructure/brokers/interface.py`

Add to existing IBroker file:

```python
from typing import Protocol

class IBrokerFactory(Protocol):
    """Factory protocol for creating broker instances."""
    def create(self, broker_type: str, config: dict) -> IBroker: ...
```

### 1.4 Move files

Move files from `src/` to `packages/pocketquant-core/src/pocketquant/core/` preserving directory structure. Use `git mv` for history.

### 1.5 Update all imports

Find-replace across moved files:

| Old import | New import |
|-----------|-----------|
| `from src.domain.` | `from pocketquant.core.domain.` |
| `from src.common.` | `from pocketquant.core.common.` |
| `from src.persistence.` | `from pocketquant.core.persistence.` |
| `from src.infrastructure.tradingview` | `from pocketquant.core.infrastructure.tradingview` |
| `from src.infrastructure.scheduling` | `from pocketquant.core.infrastructure.scheduling` |
| `from src.infrastructure.http_client` | `from pocketquant.core.infrastructure.http_client` |
| `from src.infrastructure.brokers.interface` | `from pocketquant.core.infrastructure.brokers.interface` |
| `from src.infrastructure.brokers.models` | `from pocketquant.core.infrastructure.brokers.models` |
| `from src.infrastructure.brokers.paper` | `from pocketquant.core.infrastructure.brokers.paper` |
| `from src.config` | `from pocketquant.core.config` |

### 1.6 Validate

```bash
uv sync --package pocketquant-core
uv run --package pocketquant-core python -c "from pocketquant.core.domain.bar import Bar; print('OK')"
uv run --package pocketquant-core pyright packages/pocketquant-core/
```

## Files to Move (~110 files)

**domain/**: bar/ (6), symbol/ (2), sync_status/ (2), order/ (4), position/ (5), shared/ (4), concepts/ (13)
**common/**: cache, database, logging, mediator, messaging, time, tracing, health, rate_limit, idempotency, jobs, uuid, constants, exceptions (~30)
**persistence/**: base_repository, mongodb, redis, repositories/ (7) (~10)
**infrastructure/**: tradingview/ (4), scheduling/ (2), http_client/ (2), brokers/{interface,models,paper/} (4) (~12)
**config.py**: 1

## Risks

- **Import path mass rename**: ~200+ import statements change. Use automated find-replace + pyright validation.
- **Namespace package setup**: `pocketquant/` namespace must use implicit namespace packages (no `__init__.py` at `pocketquant/` level, only at `pocketquant/core/`).

## Todo

- [ ] Create workspace root pyproject.toml
- [ ] Create pocketquant-core package skeleton
- [ ] Move domain files (git mv)
- [ ] Move common files
- [ ] Move persistence files
- [ ] Move infrastructure files
- [ ] Move config.py
- [ ] Add IBrokerFactory protocol
- [ ] Update all imports in moved files
- [ ] `uv sync --package pocketquant-core`
- [ ] Run pyright on core package
- [ ] Commit

## Success Criteria

- `uv sync --package pocketquant-core` succeeds
- Pyright passes with 0 errors on core package
- Core has zero imports from `src.application`, `src.features`, `src.di`, `src.main`
