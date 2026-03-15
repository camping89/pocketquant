# MongoDB `_id` Field Audit Report
**Date:** 2026-03-15  
**Scope:** All MongoDB-persisted domain entities in pocketquant  
**Methodology:** Grep for `to_mongo()` and `from_mongo()` methods, inspect implementation, audit repository patterns

---

## Summary

**6 MongoDB-persisted entities found:**
1. ✅ SymbolAggregate — proper `_id` handling
2. ✅ Bar (OHLCV) — proper `_id` handling
3. ⚠️ SyncStatus — **NO `_id` field** — compound key (symbol, exchange, interval)
4. ✅ OrderAggregate — uses string ID
5. ✅ PositionAggregate — uses string ID
6. ❌ OHLCVAggregate & QuoteAggregate — **NOT persisted** (no `to_mongo()`/`from_mongo()`)

**Critical Finding:** SyncStatus upserts by compound key without `_id` field. This is intentional and appropriate for time-series sync metadata.

---

## Detailed Entity Audit

### 1. SymbolAggregate
**File:** `/Users/admin/workspace/_me/pocketquant/src/domain/symbol/aggregate.py`

| Aspect | Details |
|--------|---------|
| **Lines** | 1-119 |
| **Has `_id` field?** | ✅ YES (line 23: `id: UUID`) |
| **to_mongo() _id handling** | Lines 85-95: `"_id": str(self.id)` |
| **from_mongo() _id handling** | Lines 97-112: Reconstructs UUID from `_id`, generates new if missing (fallback) |
| **Field Type** | `UUID` (converted to string in `to_mongo()`) |
| **Repository Pattern** | SymbolRepository.upsert() — query by (symbol, exchange), not `_id` |

**Implementation quality:** Excellent. UUID → string conversion is explicit and reversible.

---

### 2. Bar (OHLCV Entity)
**File:** `/Users/admin/workspace/_me/pocketquant/src/domain/ohlcv/entities.py`

| Aspect | Details |
|--------|---------|
| **Lines** | 17-105 |
| **Has `_id` field?** | ✅ YES (line 26: `id: UUID`) |
| **to_mongo() _id handling** | Lines 51-66: `"_id": str(self.id)` |
| **from_mongo() _id handling** | Lines 68-88: Reconstructs UUID from `_id`, generates new if missing (fallback) |
| **Field Type** | `UUID` (converted to string in `to_mongo()`) |
| **Repository Pattern** | OHLCVRepository.upsert_bar/upsert_many() — query by (symbol, exchange, interval, datetime), **ignores `_id`** |

**Implementation quality:** Good. However, repository upserts by composite key (symbol/exchange/interval/datetime), not by `_id`. The `_id` in `to_mongo()` is stored but NOT used for lookups. This creates potential _id divergence.

**Repository Code** (`src/persistence/repositories/ohlcv_repository.py:40-50`):
```python
operations.append(
    UpdateOne(
        {
            "symbol": doc["symbol"],
            "exchange": doc["exchange"],
            "interval": doc["interval"],
            "datetime": doc["datetime"],
        },
        update_ops,
        upsert=True,
    )
)
```

---

### 3. SyncStatus (OHLCV Helper Entity)
**File:** `/Users/admin/workspace/_me/pocketquant/src/domain/ohlcv/entities.py`

| Aspect | Details |
|--------|---------|
| **Lines** | 107-145 |
| **Has `_id` field?** | ❌ **NO** |
| **to_mongo() _id handling** | Lines 119-130: **Does NOT include `_id`** |
| **from_mongo() _id handling** | Lines 132-144: **Does NOT read `_id`** |
| **Fields** | symbol, exchange, interval, status, last_sync_at, last_bar_at, bar_count, error_message |
| **Repository Pattern** | SyncStatusRepository.upsert() — query by compound key (symbol, exchange, interval) |

**Implementation quality:** Intentional design. SyncStatus is metadata-only with no identity beyond the compound key. MongoDB generates `_id` automatically on insert, but the entity doesn't use it.

**Repository Code** (`src/persistence/repositories/sync_status_repository.py:40-48`):
```python
await collection.update_one(
    {
        "symbol": symbol.upper(),
        "exchange": exchange.upper(),
        "interval": interval.value,
    },
    {"$set": update_doc},
    upsert=True,
)
```

**Index:** Compound unique index on (symbol, exchange, interval) — lines 73-77.

---

### 4. OrderAggregate
**File:** `/Users/admin/workspace/_me/pocketquant/src/domain/order/aggregate.py`

| Aspect | Details |
|--------|---------|
| **Lines** | 28-270 |
| **Has `_id` field?** | ✅ YES (line 34: `id: str`) |
| **to_mongo() _id handling** | Lines 230-248: `"_id": self.id` (string, no conversion) |
| **from_mongo() _id handling** | Lines 250-269: Reconstructs from `doc["_id"]` (required, no fallback) |
| **Field Type** | `str` (generated via `generate_id_str()`) |
| **Repository Pattern** | OrderRepository.save() — **uses `_id` for replace_one()** (lines 13-16) |

**Implementation quality:** Excellent. String-based UUID, used correctly in repository.

**Repository Code** (`src/persistence/repositories/order_repository.py:13-16`):
```python
async def save(self, order: OrderAggregate) -> None:
    collection = self._collection()
    await collection.replace_one({"_id": order.id}, order.to_mongo(), upsert=True)
```

---

### 5. PositionAggregate
**File:** `/Users/admin/workspace/_me/pocketquant/src/domain/position/aggregate.py`

| Aspect | Details |
|--------|---------|
| **Lines** | 22-239 |
| **Has `_id` field?** | ✅ YES (line 29: `id: str`) |
| **to_mongo() _id handling** | Lines 205-220: `"_id": self.id` (string, no conversion) |
| **from_mongo() _id handling** | Lines 222-238: Reconstructs from `doc["_id"]` (required, no fallback) |
| **Field Type** | `str` (generated via `generate_id_str()`) |
| **Repository Pattern** | PositionRepository.save() — **uses `_id` for replace_one()** (lines 13-18) |

**Implementation quality:** Excellent. String-based UUID, used correctly in repository.

**Repository Code** (`src/persistence/repositories/position_repository.py:13-18`):
```python
async def save(self, position: PositionAggregate) -> None:
    collection = self._collection()
    await collection.replace_one(
        {"_id": position.id}, position.to_mongo(), upsert=True
    )
```

---

### 6. OHLCVAggregate
**File:** `/Users/admin/workspace/_me/pocketquant/src/domain/ohlcv/aggregate.py`

**Status:** ❌ **NOT persisted** — no `to_mongo()` or `from_mongo()` methods. In-memory event aggregator only.

---

### 7. QuoteAggregate
**File:** `/Users/admin/workspace/_me/pocketquant/src/domain/quote/aggregate.py`

**Status:** ❌ **NOT persisted** — no `to_mongo()` or `from_mongo()` methods. In-memory event aggregator only.

---

## Repository Upsert Pattern Summary

| Entity | Repository | Upsert Method | Query Key | Uses `_id`? |
|--------|------------|---------------|-----------|------------|
| SymbolAggregate | SymbolRepository | `update_one()` | (symbol, exchange) | ❌ NO |
| Bar | OHLCVRepository | `update_one()` / `bulk_write()` | (symbol, exchange, interval, datetime) | ❌ NO |
| SyncStatus | SyncStatusRepository | `update_one()` | (symbol, exchange, interval) | ❌ NO |
| OrderAggregate | OrderRepository | `replace_one()` | `_id` | ✅ YES |
| PositionAggregate | PositionRepository | `replace_one()` | `_id` | ✅ YES |

---

## Inconsistency Analysis

### Issue: Two Upsert Patterns

**Pattern A** (3 entities: Symbol, Bar, SyncStatus):
- Upsert by **composite domain key** (symbol/exchange/interval/datetime)
- `_id` handled by MongoDB (auto-generated or provided, not used for lookup)
- Suitable for **event/time-series data** where domain key is unique identifier

**Pattern B** (2 entities: Order, Position):
- Upsert by **`_id` field** (string UUID)
- `_id` is the primary lookup key
- Suitable for **aggregate roots** with strong identity

### Rationale Assessment

**Symbol/Bar/SyncStatus:** Domain key uniqueness is enforced via unique indexes:
- Symbol: `ix_symbols_symbol_exchange` (symbol, exchange)
- Bar: `ix_ohlcv_symbol_exchange_interval_datetime` (4-field composite)
- SyncStatus: `ix_sync_status_symbol_exchange_interval` (3-field composite)

This is correct for time-series and reference data where domain key IS the identity.

**Order/Position:** String UUID is the identity, upsert by `_id`:
- No unique domain key constraints
- Identity is explicit and centralized
- Pattern aligns with aggregate root semantics

---

## `_id` Field Distribution

| Category | Count | Status |
|----------|-------|--------|
| Has `_id` field (UUID) | 2 | SymbolAggregate, Bar |
| Has `_id` field (string) | 2 | OrderAggregate, PositionAggregate |
| NO `_id` field (compound key) | 1 | SyncStatus |
| NOT persisted | 2 | OHLCVAggregate, QuoteAggregate |

---

## Key Observations

1. **SyncStatus is intentional:** No `_id` field, upserts by (symbol, exchange, interval). This is correct for metadata tracking.

2. **UUID handling is solid:**
   - SymbolAggregate: UUID → string in `to_mongo()`, reconstructs in `from_mongo()`
   - Bar: UUID → string in `to_mongo()`, reconstructs in `from_mongo()`
   - Both have generation fallbacks

3. **String IDs in aggregates:**
   - OrderAggregate: `id: str`, direct assignment in `to_mongo()`
   - PositionAggregate: `id: str`, direct assignment in `to_mongo()`
   - Both use `replace_one()` with `_id` as lookup key

4. **Repository patterns are consistent within pattern type:**
   - Composite-key entities all use `update_one()` with domain fields
   - ID-based entities all use `replace_one()` with `_id` lookup

5. **No orphaned `_id` values:** Every entity either:
   - Explicitly manages `_id` (Symbol, Bar, Order, Position)
   - Deliberately omits it (SyncStatus)
   - Not persisted (OHLCV, Quote)

---

## Risk Assessment

**Low Risk:** Current `_id` patterns are intentional and appropriately differentiated:
- Time-series entities (Symbol, Bar) use domain key + auto-generated `_id`
- Aggregate roots (Order, Position) use explicit string `_id`
- Metadata (SyncStatus) uses domain key only

**Potential Scope for Refactoring:**
- Bar entity upserts by composite key (symbol/exchange/interval/datetime), but `to_mongo()` includes `_id`. **Divergence risk:** If a Bar is updated after initial insert, a new UUID is generated on each create, but MongoDB upsert uses composite key, so the stored `_id` remains stale. Consider: Should Bar use `_id`-based upsert for consistency with OrderAggregate/PositionAggregate?

---

## Questions to Resolve

1. **Bar entity identity:** Is the UUID in `Bar.id` ever used for lookups, or is it purely for in-memory reference? If never used in queries, consider removing `_id` from `to_mongo()` to match SyncStatus pattern.

2. **Symbol repository:** Does Symbol ever have a unique ID across multiple (symbol, exchange) pairs (i.e., should Symbol use UUID as primary identity like Order/Position)?

3. **Indexing:** All entities have proper unique indexes on their lookup keys. Are these indexes created at startup (via `ensure_indexes()`)? Verify this is called on app boot.

