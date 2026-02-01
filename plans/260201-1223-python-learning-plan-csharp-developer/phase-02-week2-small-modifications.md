# Phase 2: Small Modifications (Week 2)

## Context
- **Parent Plan:** [plan.md](./plan.md)
- **Depends On:** [Phase 1](./phase-01-week1-read-understand-patterns.md)
- **Duration:** ~5 hours total

## Overview

| Field | Value |
|-------|-------|
| Priority | P1 - Practice |
| Status | pending |
| Goal | Make safe modifications to existing code |

**Philosophy:** Low-risk changes to build muscle memory. Break things safely.

---

## Exercise 2.1: Add Structured Logging to Handler

**Objective:** Learn structlog pattern and logger usage

**Files to Modify:**
```
src/features/market_data/ohlcv/handler.py      # Target file
src/common/logging/setup.py                    # Reference: logger setup
src/features/market_data/sync/handler.py       # Reference: logging examples
```

**Task:**
1. Read how `get_logger(__name__)` is used in sync/handler.py
2. Open `ohlcv/handler.py` (GetOHLCVHandler)
3. Add logging at start and end of `handle()` method:
   ```python
   logger.info("ohlcv.query.started", symbol=request.symbol, exchange=request.exchange)
   # ... existing code ...
   logger.info("ohlcv.query.completed", symbol=request.symbol, bars_count=len(result))
   ```

**Pattern Explanation (WHY):**
Structured logging uses key-value pairs instead of string formatting:
- Searchable in log aggregators (Elasticsearch, Loki)
- No string interpolation overhead if log level disabled
- Consistent format across codebase

**C# Comparison:**
```csharp
// Serilog structured logging
_logger.Information("OHLCV query started for {Symbol} on {Exchange}", symbol, exchange);
_logger.Information("OHLCV query completed with {BarsCount} bars", result.Count);
```

**❌ BAD Alternative:**
```python
# String formatting - not searchable
logger.info(f"OHLCV query started for {symbol} on {exchange}")
print(f"Query completed: {len(result)} bars")  # NEVER use print for logging
```

**❌ WORST Alternative:**
```python
# No logging at all - blind debugging
async def handle(self, request):
    # How do you debug production issues?
    return await self._fetch_data(request)
```

**Success Criteria:**
- [ ] Added structured logging to GetOHLCVHandler
- [ ] Used `get_logger(__name__)` pattern
- [ ] Log messages use key=value format (not f-strings)
- [ ] `pyright src/features/market_data/ohlcv/` passes

---

## Exercise 2.2: Add Field to Existing DTO

**Objective:** Learn Pydantic model modification and type hints

**Files to Modify:**
```
src/features/market_data/sync/dto.py           # Target: SyncResult
src/features/market_data/sync/handler.py       # Update handler to populate field
```

**Task:**
1. Open `sync/dto.py`, find `SyncResult` dataclass
2. Add new field: `sync_duration_ms: int | None = None`
3. In `handler.py`, capture timing:
   ```python
   from time import perf_counter

   async def handle(self, request):
       start = perf_counter()
       # ... existing code ...
       duration_ms = int((perf_counter() - start) * 1000)

       return SyncResult(
           # ... existing fields ...
           sync_duration_ms=duration_ms,
       )
   ```

**Pattern Explanation (WHY):**
DTOs (Data Transfer Objects) are response contracts:
- Type hints document API response shape
- Optional fields use `| None` with default
- Pydantic validates at runtime

**C# Comparison:**
```csharp
public record SyncResult {
    public string Symbol { get; init; }
    public int? SyncDurationMs { get; init; }  // Nullable
}
```

**❌ BAD Alternative:**
```python
# Dictionary - no type safety
return {"symbol": symbol, "duration": duration}  # Typo "duraton" won't be caught
```

**❌ WORST Alternative:**
```python
# Tuple - positional, error-prone
return (symbol, exchange, duration)  # What's index 2 again?
```

**Success Criteria:**
- [ ] Added `sync_duration_ms` field to SyncResult
- [ ] Handler populates the new field
- [ ] `pyright src/features/market_data/sync/` passes
- [ ] `ruff check src/features/market_data/sync/` passes

---

## Exercise 2.3: Subscribe to Existing Domain Event

**Objective:** Learn EventBus subscription pattern

**Files to Modify:**
```
src/main.py                                    # Add subscription
src/domain/ohlcv/ohlcv_event.py               # Reference: HistoricalDataSyncedEvent
```

**Files to Create:**
```
src/features/market_data/subscribers.py        # New subscriber module
```

**Task:**
1. Create `subscribers.py`:
   ```python
   from src.common.logging import get_logger
   from src.domain.ohlcv.ohlcv_event import HistoricalDataSyncedEvent

   logger = get_logger(__name__)

   async def on_historical_data_synced(event: HistoricalDataSyncedEvent) -> None:
       """Log when historical data sync completes."""
       logger.info(
           "subscriber.data_synced",
           symbol=event.symbol,
           exchange=event.exchange,
           bars_count=event.bars_count,
       )
   ```

2. In `main.py` lifespan, after EventBus creation:
   ```python
   from src.features.market_data.subscribers import on_historical_data_synced
   from src.domain.ohlcv.ohlcv_event import HistoricalDataSyncedEvent

   event_bus.subscribe(HistoricalDataSyncedEvent, on_historical_data_synced)
   ```

**Pattern Explanation (WHY):**
Subscribers are decoupled from publishers:
- SyncSymbolHandler doesn't know who listens
- Adding subscribers doesn't change handler code
- Easy to add notifications, analytics, etc.

**C# Comparison:**
```csharp
// MediatR notification handler
public class SyncNotificationHandler : INotificationHandler<HistoricalDataSyncedEvent> {
    public Task Handle(HistoricalDataSyncedEvent notification, CancellationToken ct) {
        _logger.LogInformation("Data synced: {Symbol}", notification.Symbol);
        return Task.CompletedTask;
    }
}
```

**❌ BAD Alternative:**
```python
# Direct call in handler - tight coupling
class SyncSymbolHandler:
    async def handle(self, request):
        # ... sync logic ...
        await self._notification_service.notify(...)  # Handler knows about notifications
```

**Success Criteria:**
- [ ] Created `subscribers.py` with typed event handler
- [ ] Registered subscription in `main.py`
- [ ] Sync endpoint triggers subscriber log
- [ ] `pyright src/features/market_data/subscribers.py` passes

---

## Exercise 2.4: Add Validation to Command

**Objective:** Learn `__post_init__` validation pattern

**Files to Modify:**
```
src/features/market_data/sync/command.py       # Target: SyncSymbolCommand
```

**Task:**
1. Open `command.py`, find `SyncSymbolCommand`
2. Add validation in `__post_init__`:
   ```python
   @dataclass
   class SyncSymbolCommand:
       symbol: str
       exchange: str
       interval: str = "1d"
       n_bars: int = 500

       def __post_init__(self) -> None:
           if not self.symbol:
               raise ValueError("Symbol is required")
           if not self.exchange:
               raise ValueError("Exchange is required")
           if self.n_bars < 1 or self.n_bars > 5000:
               raise ValueError("n_bars must be between 1 and 5000")

           # Normalize to uppercase
           object.__setattr__(self, "symbol", self.symbol.upper())
           object.__setattr__(self, "exchange", self.exchange.upper())
   ```

**Pattern Explanation (WHY):**
`__post_init__` runs after dataclass `__init__`:
- Validate invariants early (fail fast)
- Normalize data (uppercase symbols)
- Keep validation close to data definition

**Note:** For frozen dataclasses, use `object.__setattr__()` to modify fields in `__post_init__`.

**C# Comparison:**
```csharp
public record SyncSymbolCommand {
    public string Symbol { get; init; }

    public SyncSymbolCommand {
        if (string.IsNullOrEmpty(Symbol))
            throw new ArgumentException("Symbol is required");
        Symbol = Symbol.ToUpper();
    }
}
```

**❌ BAD Alternative:**
```python
# Validation in handler - too late, duplicated
class SyncSymbolHandler:
    async def handle(self, request):
        if not request.symbol:  # Validation scattered in handler
            raise ValueError("Symbol required")
```

**❌ WORST Alternative:**
```python
# No validation - garbage in, garbage out
@dataclass
class SyncSymbolCommand:
    symbol: str  # Could be empty, None, or "aapl" (lowercase)
```

**Success Criteria:**
- [ ] Added `__post_init__` validation to SyncSymbolCommand
- [ ] Invalid commands raise `ValueError` with clear message
- [ ] Symbol/exchange normalized to uppercase
- [ ] `pyright src/features/market_data/sync/command.py` passes

---

## Week 2 Checklist

- [ ] Exercise 2.1: Structured logging added
- [ ] Exercise 2.2: DTO field added with timing
- [ ] Exercise 2.3: Event subscriber created
- [ ] Exercise 2.4: Command validation added
- [ ] All modified files pass `pyright` and `ruff check`

## Verification Commands

```bash
# Type check modified files
pyright src/features/market_data/

# Lint check
ruff check src/features/market_data/

# Run app to test
uvicorn src.main:app --reload
# POST /api/v1/market-data/sync with {"symbol": "aapl", "exchange": "nasdaq"}
# Check logs for subscriber output
```

## Next Phase

→ [Phase 3: Create New Features](./phase-03-week3-create-new-features.md)
