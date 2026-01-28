# Phase 3: Inline Symbol Repository

## Context
- `SymbolRepository` (89 LOC) called by DataSyncService and routes.py
- Simple CRUD operations, ideal for direct inlining

## Overview
- **Priority:** P2
- **Status:** Pending
- **Effort:** 30 min
- **Depends on:** Phase 2 completed

## Key Insights
- SymbolRepository has 4 methods: `upsert`, `get`, `get_all`, `delete`
- Main callers: `DataSyncService.sync_symbol()` (upsert), `routes.py` (get_all)
- Simple enough to inline directly without helper methods

## Requirements

### Functional
- Inline `upsert()` into DataSyncService
- Inline `get_all()` into routes.py
- Remove SymbolRepository dependency

### Non-functional
- No behavior change
- Maintain logging

## Files

### Modify
- `src/features/market_data/services/data_sync_service.py` (inline upsert)
- `src/features/market_data/api/routes.py` (inline get_all)

### Delete (Phase 5)
- `src/features/market_data/repositories/symbol_repository.py`

## Method Migration Map

| Method | Current Caller | Move To |
|--------|---------------|---------|
| `upsert()` | DataSyncService | Inline in DataSyncService |
| `get()` | (unused) | DROP |
| `get_all()` | routes.py | Inline in routes.py handler |
| `delete()` | (unused) | DROP |

## Implementation Steps

### Step 1: Inline upsert into DataSyncService

**Current call in sync_symbol():**
```python
await SymbolRepository.upsert(
    SymbolCreate(symbol=symbol, exchange=exchange, is_active=True)
)
```

**Replace with inline:**
```python
# Add to DataSyncService class constants
SYMBOLS_COLLECTION = "symbols"

# Inline in sync_symbol() after upsert_many
symbols_collection = Database.get_collection(self.SYMBOLS_COLLECTION)
symbol_doc = {
    "symbol": symbol,
    "exchange": exchange,
    "is_active": True,
    "updated_at": datetime.now(UTC),
}
await symbols_collection.update_one(
    {"symbol": symbol, "exchange": exchange},
    {"$set": symbol_doc, "$setOnInsert": {"created_at": datetime.now(UTC)}},
    upsert=True,
)
```

### Step 2: Inline get_all into routes.py

**Current call in list_symbols():**
```python
symbols = await SymbolRepository.get_all(exchange=exchange)
```

**Replace with inline:**
```python
from src.common.database import Database
from src.features.market_data.models.symbol import Symbol

@router.get("/symbols")
async def list_symbols(
    exchange: str | None = Query(default=None, description="Filter by exchange"),
) -> list[dict]:
    collection = Database.get_collection("symbols")

    query = {}
    if exchange:
        query["exchange"] = exchange.upper()

    cursor = collection.find(query).sort("symbol", 1)

    return [
        {
            "symbol": doc["symbol"],
            "exchange": doc["exchange"],
            "name": doc.get("name"),
            "asset_type": doc.get("asset_type"),
            "is_active": doc.get("is_active", True),
        }
        async for doc in cursor
    ]
```

### Step 3: Remove SymbolRepository imports
Remove from:
- `data_sync_service.py`
- `routes.py`

## Todo

- [ ] Add SYMBOLS_COLLECTION constant to DataSyncService
- [ ] Inline symbol upsert in sync_symbol()
- [ ] Add Database import to routes.py
- [ ] Inline get_all in list_symbols() handler
- [ ] Remove SymbolRepository imports
- [ ] Run tests

## Success Criteria
- [ ] No imports from `repositories/symbol_repository`
- [ ] Symbol upsert works in sync flow
- [ ] /symbols endpoint returns data
- [ ] All tests pass

## Risks
- None - straightforward CRUD inlining
