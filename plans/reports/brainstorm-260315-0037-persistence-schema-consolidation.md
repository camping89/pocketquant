# Brainstorm: Persistence Schema Consolidation

## Problem Statement

Inconsistent persistence layer: mixed `_id` strategies (UUID7 string vs MongoDB ObjectId), redundant Pydantic schema hierarchy (`*Base` + child classes), duplication between domain entities (dataclasses) and persistence schemas (Pydantic). Need unified approach.

## Decisions Made

### 1. Uniform `_id` — UUID7 string everywhere
- **Status**: Code smell / consistency fix (no active bugs)
- All collections use `str(uuid7())` as `_id`
- String format (36 chars) — accepted tradeoff for readability in mongosh
- No BSON Binary UUID optimization needed at current scale

### 2. UUID7 confirmed
- Python 3.14 native `uuid7()` via `src/common/uuid.py`
- Not v4, not ULID

### 3. Kill `*Base` + persistence schemas entirely
- Delete `src/persistence/schemas/symbol_schema.py`
- Delete `src/persistence/schemas/ohlcv_schema.py` (move `OHLCVResponse`, `SyncStatus` elsewhere)
- Domain entities become the single source of truth
- No more `SymbolBase`/`Symbol`, `OHLCVBase`/`OHLCV` split

### 4. Domain entities → Pydantic BaseModel (full migration)
- **All** domain entities AND aggregates: dataclass → Pydantic BaseModel
- Entities get `to_mongo()` / `from_mongo()` methods
- `@dataclass(eq=False)` → `model_config = ConfigDict(...)`
- `field(default_factory=...)` → `Field(default_factory=...)`
- `_events: list` → `PrivateAttr(default_factory=list)`
- `replace(obj, ...)` → `obj.model_copy(update={...})`
- Pydantic gives field validation + serialization in one place

### 5. Timestamps
- **`created_at`**: on domain entity, `Field(default_factory=_utc_now)`. Set once at creation. Persisted via `to_mongo()`. Redundant with UUID7 timestamp — accepted for queryability (`$gte` on `created_at`).
- **`updated_at`**: NOT on domain entity. Repo always `$set`s `updated_at: datetime.now(UTC)` server-side in update/upsert operations. Entity never carries stale `updated_at`.
- **`id`**: UUID7, stored as string `_id` in MongoDB.

### 6. Data flow (new)
```
WRITE: Handler creates/modifies domain entity → repo calls entity.to_mongo() → $set doc + $set updated_at → MongoDB
READ:  MongoDB doc → Entity.from_mongo(doc) → domain entity (created_at populated from DB)
```

## Scope of Changes

### Domain layer (`src/domain/`)
- `Bar` (entity) — dataclass → Pydantic, add `created_at`, `to_mongo()`, `from_mongo()`
- `SyncStatus` (entity) — dataclass → Pydantic, add methods
- `SymbolAggregate` — dataclass → Pydantic, `_events` → `PrivateAttr`, add persistence methods
- `OHLCVAggregate` — same as above
- `PositionAggregate`, `OrderAggregate`, `QuoteAggregate` — same pattern
- All value objects using `@dataclass` — evaluate case by case (some may stay dataclass if never persisted)

### Persistence layer (`src/persistence/`)
- Delete `schemas/symbol_schema.py`
- Delete `schemas/ohlcv_schema.py` (relocate `OHLCVResponse` to API/response layer)
- Update `SymbolRepository` — use `SymbolAggregate.to_mongo()` instead of manual dict building
- Update `OHLCVRepository` — use `Bar.to_mongo()` instead of `OHLCV` schema promotion
- All repos: add `$set updated_at` in every update/upsert operation

### Handler layer
- Remove imports of `SymbolBase`, `OHLCVBase`
- Construct domain entities directly

## Risks
- **Migration size**: touching all domain entities + all repos + all handlers. High blast radius.
- **Pydantic `PrivateAttr` quirks**: `_events` won't show in `model_dump()` (good) but init syntax differs
- **Existing tests**: tests using dataclass construction need updating for Pydantic
- **`eq=False` behavior**: Pydantic default equality is by value; need explicit `__eq__`/`__hash__` override

## Unresolved Questions
- Where does `OHLCVResponse` (API response model) move to? Likely `src/features/market_data/` or a shared API schemas module.
- Should value objects (`SymbolInfo`, `BarRange`, `Interval`) also become Pydantic? They're never persisted directly.
- `SyncStatus` schema exists in both domain and persistence — which survives?
