# Python ABC Interface Patterns for Provider Abstractions

## Executive Summary
Python ABC with `@abstractmethod` is the standard approach for defining provider interfaces. Async methods require decorator stacking: `@abstractmethod async def`. Protocols offer structural typing alternative when inheritance isn't available.

## 1. Defining IDataProvider Interface

### Standard ABC Pattern
```python
from abc import ABC, abstractmethod
from typing import Awaitable
from src.features.market_data.models.ohlcv import OHLCVCreate, Interval

class IDataProvider(ABC):
    @abstractmethod
    async def fetch_ohlcv(
        self,
        symbol: str,
        exchange: str,
        interval: Interval,
        n_bars: int = 1000,
    ) -> list[OHLCVCreate]:
        """Fetch OHLCV bars from provider."""
        ...

    @abstractmethod
    async def search_symbols(self, query: str, exchange: str | None = None) -> list[dict]:
        """Search available symbols."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Clean up resources."""
        ...
```

**Key Points:**
- `@abstractmethod` decorator (no need for `async` keyword on decorator)
- Type hints required for all parameters and return types
- Works with mypy static type checking
- Enforces implementation in subclasses at instantiation time

## 2. Type Hints for Async Abstract Methods

### Proper Annotation
```python
# ✓ Correct: Type hint on async function signature
@abstractmethod
async def fetch_ohlcv(...) -> list[OHLCVCreate]: ...

# ✓ Alternative: Explicit Awaitable type
@abstractmethod
def fetch_ohlcv(...) -> Awaitable[list[OHLCVCreate]]: ...
```

**Difference:**
- `async def ... -> T` implies the function is async-native
- `def ... -> Awaitable[T]` allows both async and sync callable wrapping
- Prefer first for provider methods; second only for flexible callback types

## 3. Infrastructure Layer Organization

### Minimal Refactor (Preserve Existing Code)
```
src/features/market_data/
├── providers/
│   ├── __init__.py
│   ├── base.py              # NEW: IDataProvider ABC
│   ├── tradingview.py       # MODIFY: Add `class TradingViewProvider(IDataProvider)`
│   └── tradingview_ws.py
├── services/
│   └── data_sync_service.py # MODIFY: Type hint with IDataProvider
```

**Migration Strategy:**
1. Create `base.py` with `IDataProvider` ABC
2. Add `(IDataProvider)` to existing `TradingViewProvider` class
3. No code removal—just add inheritance, mypy validates compatibility
4. Services inject via interface type hint: `provider: IDataProvider`

## 4. Making Providers Implement Interfaces Without Breaking

### Non-Breaking Implementation
```python
# BEFORE (no changes needed—leave as is)
class TradingViewProvider:
    async def fetch_ohlcv(...) -> list[OHLCVCreate]: ...

# AFTER (only add inheritance)
class TradingViewProvider(IDataProvider):
    async def fetch_ohlcv(...) -> list[OHLCVCreate]: ...
    # All methods already match—mypy validates, no runtime breaks
```

**Why Safe:**
- ABC is structural validation layer; signatures already match
- No method removal/renaming in existing code
- Services switch to `IDataProvider` type hints gradually
- Backward compatible: `TradingViewProvider()` still works everywhere

## 5. Best Practices

| Practice | Rationale |
|----------|-----------|
| Put ABC in separate `base.py` | Avoids circular imports; clean organization |
| Use ABC over Protocol | Clear inheritance hierarchy; easier discoverability |
| Type hint dependencies with interface | `service: DataSyncService(provider: IDataProvider)` |
| Keep async/sync boundary clear | Don't mix `@abstractmethod` with sync wrapper methods |
| No default implementations in ABC | Forces explicit override; documents contract clearly |

## Trade-offs: ABC vs Protocol

| Aspect | ABC | Protocol |
|--------|-----|----------|
| Inheritance Required | Yes (explicit) | No (structural) |
| Mypy Support | Full | Full |
| Discovery | Better (class hierarchy) | Harder (implicit) |
| Refactor Scope | Larger (inheritance needed) | Smaller (no changes) |

**Recommendation:** Use ABC. Existing provider already has methods; minimal refactor; clear contract.

## Implementation Checklist

- [ ] Create `src/features/market_data/providers/base.py` with `IDataProvider`
- [ ] Add `(IDataProvider)` to `TradingViewProvider` class
- [ ] Type hint `DataSyncService.provider: IDataProvider`
- [ ] Run `mypy src/` to validate (should pass without changes)
- [ ] Update imports in services that use provider

---

**Unresolved Questions:**
- How to handle WebSocket provider (`tradingview_ws.py`)? Same interface or separate?
