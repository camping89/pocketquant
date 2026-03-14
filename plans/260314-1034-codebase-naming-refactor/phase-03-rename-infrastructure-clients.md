# Phase 3: Rename Infrastructure Clients to `*Client`

**Priority:** Medium
**Status:** completed
**Depends on:** Phase 1 (DI paths), Phase 2 (QuoteAppService already renamed)

## Overview

Rename 2 TradingView infrastructure classes from `*Provider` to `*Client` to disambiguate from Dishka DI providers. File and class renames.

## Renames

| Old Class | New Class | Old File | New File |
|---|---|---|---|
| `TradingViewProvider` | `TradingViewClient` | `src/infrastructure/tradingview/provider.py` | `src/infrastructure/tradingview/tradingview_client.py` |
| `TradingViewWebSocketProvider` | `TradingViewWebSocketClient` | `src/infrastructure/tradingview/websocket.py` | `src/infrastructure/tradingview/tradingview_websocket_client.py` |

## Files to Update

### 1. TradingViewProvider -> TradingViewClient

**Rename file + class**, then update importers:

| File | Change |
|---|---|
| `src/infrastructure/tradingview/__init__.py` | Import path + `__all__` entry |
| `src/di/infrastructure.py` | Import path + type hint + factory method return type |
| `src/features/market_data/sync/sync_one/handler.py` | Import path + `__init__` type hint |
| `testscripts/run_sync_jobs.py` | Import path + instantiation |

### 2. TradingViewWebSocketProvider -> TradingViewWebSocketClient

**Rename file + class**, then update importers:

| File | Change |
|---|---|
| `src/infrastructure/tradingview/__init__.py` | Import path + `__all__` entry |
| `src/application/market_data/quote_app_service.py` | Import path + instantiation (after Phase 2 rename) |
| `tests/integration/tradingview/test_websocket_integration.py` | Import path + all instantiations (3 occurrences) |
| `tests/unit/infrastructure/tradingview/test_websocket.py` | Import + class name in test class docstring + ~20 instantiations |
| `testscripts/run_stream_quotes.py` | Import path + instantiation |

## Detailed Changes

### `src/infrastructure/tradingview/__init__.py`

```python
# OLD
from src.infrastructure.tradingview.provider import TradingViewProvider
from src.infrastructure.tradingview.websocket import TradingViewWebSocketProvider
__all__ = ["IDataProvider", "TradingViewProvider", "TradingViewWebSocketProvider"]

# NEW
from src.infrastructure.tradingview.tradingview_client import TradingViewClient
from src.infrastructure.tradingview.tradingview_websocket_client import TradingViewWebSocketClient
__all__ = ["IDataProvider", "TradingViewClient", "TradingViewWebSocketClient"]
```

### `src/di/infrastructure.py`

```python
# OLD
from src.infrastructure.tradingview import TradingViewProvider
def get_tv_provider(self, settings: Settings) -> TradingViewProvider:
    return TradingViewProvider(settings=settings)

# NEW
from src.infrastructure.tradingview import TradingViewClient
def get_tv_client(self, settings: Settings) -> TradingViewClient:
    return TradingViewClient(settings=settings)
```

### `src/features/market_data/sync/sync_one/handler.py`

```python
# OLD
from src.infrastructure.tradingview import TradingViewProvider
def __init__(self, provider: TradingViewProvider, ...):

# NEW
from src.infrastructure.tradingview import TradingViewClient
def __init__(self, provider: TradingViewClient, ...):
```

### `src/application/market_data/quote_app_service.py` (after Phase 2)

```python
# OLD
from src.infrastructure.tradingview import TradingViewWebSocketProvider
self.provider = TradingViewWebSocketProvider()

# NEW
from src.infrastructure.tradingview import TradingViewWebSocketClient
self.provider = TradingViewWebSocketClient()
```

### Test files

In `tests/unit/infrastructure/tradingview/test_websocket.py`:
- Replace all `TradingViewWebSocketProvider` with `TradingViewWebSocketClient` (~25 occurrences)
- Update import from `src.infrastructure.tradingview.websocket` to `src.infrastructure.tradingview.tradingview_websocket_client`
- Update test class docstring

In `tests/integration/tradingview/test_websocket_integration.py`:
- Replace import and 3 instantiations

## Implementation Steps

1. `git mv src/infrastructure/tradingview/provider.py src/infrastructure/tradingview/tradingview_client.py`
2. Rename class `TradingViewProvider` -> `TradingViewClient` in the file
3. Update 4 importing files
4. `git mv src/infrastructure/tradingview/websocket.py src/infrastructure/tradingview/tradingview_websocket_client.py`
5. Rename class `TradingViewWebSocketProvider` -> `TradingViewWebSocketClient` in the file
6. Update 5 importing files (including 2 test files)
7. Update `src/infrastructure/tradingview/__init__.py`

## Todo

- [x] Rename TradingViewProvider -> TradingViewClient (file + class + 4 importers)
- [x] Rename TradingViewWebSocketProvider -> TradingViewWebSocketClient (file + class + 5 importers)
- [x] Update `src/infrastructure/tradingview/__init__.py` re-exports
- [x] Run `ruff check src/ tests/`
- [x] Run `pyright src/`
- [x] Run `pytest`

## Success Criteria

- No references to `TradingViewProvider` or `TradingViewWebSocketProvider` in codebase
- `from src.infrastructure.tradingview import TradingViewClient` works
- DI resolves `TradingViewClient` correctly
- All tests pass (unit + integration)
