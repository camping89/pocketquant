# Phase 1A: Infrastructure Interfaces

## Context
- [ABC Interfaces Research](./research/researcher-02-abc-interfaces.md)
- Current: `TradingViewProvider` has no interface, concrete class only

## Overview
- **Priority:** P2
- **Status:** Pending
- **Effort:** 30 min
- **Parallelizable:** Yes (no file overlap with 1B, 1C)

## Key Insights
- ABC preferred over Protocol (clear inheritance hierarchy)
- `@abstractmethod` + `async def` for async methods
- Non-breaking: just add inheritance to existing class

## Requirements

### Functional
- Create `IDataProvider` ABC with `fetch_ohlcv`, `search_symbols`, `close` methods
- `TradingViewProvider` implements `IDataProvider`

### Non-functional
- mypy validates interface compliance
- No runtime behavior change

## Files

### Create
- `src/features/market_data/providers/base.py` (~35 LOC)

### Modify
- `src/features/market_data/providers/tradingview.py` (add inheritance)

## Implementation Steps

### Step 1: Create base.py with IDataProvider ABC
```python
# src/features/market_data/providers/base.py
from abc import ABC, abstractmethod
from src.features.market_data.models.ohlcv import Interval, OHLCVCreate

class IDataProvider(ABC):
    @abstractmethod
    async def fetch_ohlcv(
        self,
        symbol: str,
        exchange: str,
        interval: Interval,
        n_bars: int = 1000,
    ) -> list[OHLCVCreate]:
        """Fetch OHLCV bars from data provider."""
        ...

    @abstractmethod
    async def search_symbols(
        self,
        query: str,
        exchange: str | None = None,
    ) -> list[dict]:
        """Search available symbols."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Clean up resources."""
        ...
```

### Step 2: Update TradingViewProvider to implement interface
```python
# Add import
from src.features.market_data.providers.base import IDataProvider

# Change class declaration
class TradingViewProvider(IDataProvider):
    # ... existing implementation (no other changes needed)
```

## Todo

- [ ] Create `providers/base.py` with IDataProvider ABC
- [ ] Add `(IDataProvider)` inheritance to TradingViewProvider
- [ ] Run `mypy src/features/market_data/providers/`
- [ ] Run tests

## Success Criteria
- [ ] `IDataProvider` ABC exists with 3 abstract methods
- [ ] `TradingViewProvider(IDataProvider)` passes mypy
- [ ] All existing tests pass

## Risks
- Circular import if base.py imports from models incorrectly
- Mitigation: Only import from models, not from other providers
