# Phase 1: Market Data Sync Commands

## Context

- Parent: [plan.md](plan.md)
- Decision: [decision-merge-pydantic-request-command-for-cqrs.md](../reports/decision-merge-pydantic-request-command-for-cqrs.md)

## Overview

- **Priority:** P1 (foundational)
- **Status:** pending
- **Effort:** 45m

Convert market_data/sync commands from dataclass to Pydantic and update routes to use commands directly.

## Files to Modify

| File | Changes |
|------|---------|
| `src/features/market_data/sync/command.py` | dataclass → Pydantic BaseModel |
| `src/features/market_data/sync/dto.py` | dataclass → Pydantic BaseModel |
| `src/features/market_data/sync/handler.py` | Return SyncResponse directly |
| `src/features/market_data/api/routes.py` | Remove SyncRequest/BulkSyncRequest, use commands |

## Implementation Steps

### 1. Convert command.py (dataclass → Pydantic)

Before:
```python
from dataclasses import dataclass

@dataclass
class SyncSymbolCommand:
    symbol: str
    exchange: str
    interval: str = "1d"
    n_bars: int = 500
    background: bool = False
```

After:
```python
from pydantic import BaseModel, Field
from src.common.constants import LIMIT_TVDATAFEED_MAX_BARS
from src.features.market_data.models.ohlcv import Interval

class SyncSymbolCommand(BaseModel):
    """Sync historical OHLCV data for a single symbol."""
    symbol: str = Field(..., description="Trading symbol (e.g., AAPL, BTCUSD)")
    exchange: str = Field(..., description="Exchange name (e.g., NASDAQ, BINANCE)")
    interval: Interval = Field(default=Interval.DAY_1, description="Time interval")
    n_bars: int = Field(default=LIMIT_TVDATAFEED_MAX_BARS, ge=1, le=LIMIT_TVDATAFEED_MAX_BARS)

class BulkSyncCommand(BaseModel):
    """Sync multiple symbols in sequence."""
    symbols: list[dict] = Field(..., examples=[[{"symbol": "AAPL", "exchange": "NASDAQ"}]])
    interval: Interval = Field(default=Interval.DAY_1)
    n_bars: int = Field(default=LIMIT_TVDATAFEED_MAX_BARS, ge=1, le=LIMIT_TVDATAFEED_MAX_BARS)
```

### 2. Convert dto.py to Pydantic

Before:
```python
from dataclasses import dataclass

@dataclass
class SyncResult:
    symbol: str
    ...
```

After:
```python
from pydantic import BaseModel

class SyncResponse(BaseModel):
    """Result of sync operation - used as handler return and API response."""
    symbol: str
    exchange: str
    interval: str
    status: str
    bars_synced: int = 0
    total_bars: int | None = None
    last_bar_at: str | None = None
    message: str | None = None
```

### 3. Update handler.py

- Change SyncResult → SyncResponse import
- Return SyncResponse from handler (already Pydantic, route passes through)

### 4. Simplify routes.py

Before:
```python
class SyncRequest(BaseModel):
    symbol: str = Field(...)
    ...

@router.post("/sync", response_model=SyncResponse)
async def sync_symbol(request: SyncRequest, mediator: ...):
    cmd = SyncSymbolCommand(
        symbol=request.symbol,
        exchange=request.exchange,
        interval=request.interval.value,
        n_bars=request.n_bars,
    )
    result = await mediator.send(cmd)
    return SyncResponse(symbol=result.symbol, ...)
```

After:
```python
@router.post("/sync", response_model=SyncResponse)
async def sync_symbol(cmd: SyncSymbolCommand, mediator: ...):
    return await mediator.send(cmd)
```

- Remove: SyncRequest, BulkSyncRequest classes
- Keep: SyncResponse (now imported from dto.py)
- Simplify: All sync endpoints to pass-through

## Todo

- [ ] Convert command.py to Pydantic
- [ ] Convert dto.py to Pydantic (rename SyncResult → SyncResponse)
- [ ] Update handler imports and return types
- [ ] Simplify routes (remove Request classes)
- [ ] Run pyright to check types
- [ ] Test endpoints manually

## Success Criteria

- [ ] SyncSymbolCommand and BulkSyncCommand are Pydantic models
- [ ] SyncResponse is Pydantic model (was SyncResult dataclass)
- [ ] Routes use commands directly
- [ ] Handler returns SyncResponse directly
- [ ] No type errors
- [ ] OpenAPI shows correct schemas

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Interval enum mismatch | Use same Interval enum in command as routes |
| Handler type mismatch | Update Handler generic types |
| Breaking existing tests | Update test fixtures |

## Notes

- interval field uses Interval enum (not string) for validation
- Handler converts interval.value internally when needed
- background field removed from command (handled by route choice)
