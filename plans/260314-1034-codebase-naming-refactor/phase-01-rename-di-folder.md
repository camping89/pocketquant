# Phase 1: Rename DI Folder (`src/providers/` -> `src/di/`)

**Priority:** High (other phases depend on new import paths)
**Status:** completed

## Overview

Move `src/providers/` to `src/di/` and rename files to drop the `_provider` suffix. DI class names (e.g. `CoreProvider`, `TradingProvider`) stay unchanged -- only folder and filenames change.

## File Renames

| Current Path | New Path |
|---|---|
| `src/providers/__init__.py` | `src/di/__init__.py` |
| `src/providers/core_provider.py` | `src/di/core.py` |
| `src/providers/persistence_provider.py` | `src/di/persistence.py` |
| `src/providers/infrastructure_provider.py` | `src/di/infrastructure.py` |
| `src/providers/market_data_provider.py` | `src/di/market_data.py` |
| `src/providers/trading_provider.py` | `src/di/trading.py` |
| `src/providers/handler_provider.py` | `src/di/handlers.py` |

## Files to Update (imports)

### 1. `src/di/__init__.py` (self-referencing imports)

```python
# OLD
from src.providers.core_provider import CoreProvider
from src.providers.handler_provider import HandlerProvider
from src.providers.infrastructure_provider import InfrastructureProvider
from src.providers.market_data_provider import MarketDataProvider
from src.providers.persistence_provider import PersistenceProvider
from src.providers.trading_provider import TradingProvider

# NEW
from src.di.core import CoreProvider
from src.di.handlers import HandlerProvider
from src.di.infrastructure import InfrastructureProvider
from src.di.market_data import MarketDataProvider
from src.di.persistence import PersistenceProvider
from src.di.trading import TradingProvider
```

### 2. `src/container.py`

```python
# OLD
from src.providers import (CoreProvider, HandlerProvider, ...)
from src.providers.handler_provider import ALL_HANDLER_TYPES

# NEW
from src.di import (CoreProvider, HandlerProvider, ...)
from src.di.handlers import ALL_HANDLER_TYPES
```

Also update docstring: `1. Create a Provider subclass in src/di/`

### 3. No other source files import from `src.providers`

Confirmed via grep -- only `src/container.py` and `src/providers/__init__.py` reference `src.providers`. No test files import from it.

## Implementation Steps

1. `git mv src/providers src/di`
2. Rename files within `src/di/`:
   - `mv core_provider.py core.py`
   - `mv persistence_provider.py persistence.py`
   - `mv infrastructure_provider.py infrastructure.py`
   - `mv market_data_provider.py market_data.py`
   - `mv trading_provider.py trading.py`
   - `mv handler_provider.py handlers.py`
3. Update imports in `src/di/__init__.py`
4. Update imports in `src/container.py`
5. Update docstring in `src/container.py`

## Todo

- [x] git mv src/providers src/di
- [x] Rename 6 files (drop `_provider` suffix)
- [x] Update `src/di/__init__.py` imports
- [x] Update `src/container.py` imports + docstring
- [x] Run `ruff check src/di/ src/container.py`
- [x] Run `pyright src/di/ src/container.py`
- [x] Run `pytest` (smoke test)

## Success Criteria

- `from src.di import CoreProvider` works
- `from src.di.handlers import ALL_HANDLER_TYPES` works
- No remaining references to `src.providers` in source code
- All tests pass
