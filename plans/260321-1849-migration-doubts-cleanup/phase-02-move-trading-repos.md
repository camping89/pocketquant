# Phase 2: Move order_repository + position_repository to Trading Package

## Overview
- **Priority:** P1
- **Status:** completed
- **Risk:** Low — mechanical move + import updates

OrderRepository and PositionRepository are trading concerns (order lifecycle, position tracking). They import from `core.domain.order` / `core.domain.position` which is fine — trading depends on core.

## Files to Move

| From | To |
|------|----|
| `packages/pocketquant-core/src/pocketquant/core/persistence/repositories/order_repository.py` | `packages/pocketquant-trading/src/pocketquant/trading/persistence/order_repository.py` |
| `packages/pocketquant-core/src/pocketquant/core/persistence/repositories/position_repository.py` | `packages/pocketquant-trading/src/pocketquant/trading/persistence/position_repository.py` |

## Files to Create

### `packages/pocketquant-trading/src/pocketquant/trading/persistence/__init__.py`
```python
"""Trading persistence — order and position repositories."""

from pocketquant.trading.persistence.order_repository import OrderRepository
from pocketquant.trading.persistence.position_repository import PositionRepository

__all__ = ["OrderRepository", "PositionRepository"]
```

## Files to Update (Import Changes)

All imports change from:
```python
from pocketquant.core.persistence.repositories.order_repository import OrderRepository
from pocketquant.core.persistence.repositories.position_repository import PositionRepository
```
To:
```python
from pocketquant.trading.persistence.order_repository import OrderRepository
from pocketquant.trading.persistence.position_repository import PositionRepository
```

### 6 files need import updates:

1. **`packages/pocketquant-api/src/pocketquant/api/di/persistence.py`** (lines 20-21)
2. **`packages/pocketquant-api/src/pocketquant/api/di/trading.py`** (lines 18-19)
3. **`packages/pocketquant-api/src/pocketquant/api/main_extensions.py`** (lines 31-32)
4. **`packages/pocketquant-trading/src/pocketquant/trading/app_services/order_app_service.py`** (line 11)
5. **`packages/pocketquant-trading/src/pocketquant/trading/app_services/position_app_service.py`** (line 10)
6. **`packages/pocketquant-core/src/pocketquant/core/persistence/repositories/__init__.py`** — remove OrderRepository and PositionRepository exports

### Internal imports within moved files
The moved files themselves import from `pocketquant.core.*` (BaseRepository, domain entities, constants). These stay unchanged — trading depends on core.

## Verification
```bash
uv run lint-imports
uv run python -c "from pocketquant.trading.persistence import OrderRepository, PositionRepository; print('OK')"
```

## Todo
- [x] Create `trading/persistence/` dir with `__init__.py`
- [x] Move order_repository.py to trading/persistence/
- [x] Move position_repository.py to trading/persistence/
- [x] Update imports in di/persistence.py
- [x] Update imports in di/trading.py
- [x] Update imports in main_extensions.py
- [x] Update imports in order_app_service.py
- [x] Update imports in position_app_service.py
- [x] Update core repositories/__init__.py — remove moved exports
- [x] Run lint-imports — verify clean
