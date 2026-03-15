# Phase 1: OHLCV Domain + Repo

## Overview
- **Priority**: HIGH — most complex, sets the pattern for all other phases
- **Status**: completed

## Context
- Brainstorm: `plans/reports/brainstorm-260315-0037-persistence-schema-consolidation.md`
- Current schema: `src/persistence/schemas/ohlcv_schema.py` — `OHLCVBase`, `OHLCV`, `SyncStatus` (Pydantic), `OHLCVResponse`
- Current entity: `src/domain/ohlcv/entities.py` — `Bar` (dataclass), `SyncStatus` (dataclass)
- Current repo: `src/persistence/repositories/ohlcv_repository.py`
- Current sync status repo: `src/persistence/repositories/sync_status_repository.py`

## Key Insights

- `OHLCVBase` is used in handler, infra (tradingview), and repo as input DTO
- `OHLCV` (child schema) is used ONLY in repo `upsert_many` and `upsert_bar` for `to_mongo()` serialization
- `Bar` entity is the read-path return type — repo already converts doc → `Bar` via `_doc_to_bar()`
- `SyncStatus` exists in BOTH domain and schema — domain version survives
- `OHLCVResponse` is API response — relocate to route file

## Files to Modify

| File | Action |
|------|--------|
| `src/domain/ohlcv/entities.py` | Migrate `Bar` + `SyncStatus` from dataclass → Pydantic |
| `src/persistence/repositories/ohlcv_repository.py` | Use `Bar.to_mongo()`/`Bar.from_mongo()`, remove schema imports |
| `src/persistence/repositories/sync_status_repository.py` | Use `SyncStatus.from_mongo()`, remove manual mapper |
| `src/features/market_data/sync/sync_one/handler.py` | Replace `SymbolBase`/`OHLCVBase` with domain entities |
| `src/infrastructure/tradingview/base.py` | Replace `OHLCVBase` import with `Bar` |
| `src/infrastructure/tradingview/tradingview_client.py` | Replace `OHLCVBase` import with `Bar` |
| `src/features/market_data/ohlcv/get_ohlcv/route.py` | Inline `OHLCVResponse` |
| `src/domain/ohlcv/__init__.py` | Update exports |

## Files to Delete
| File | Reason |
|------|--------|
| `src/persistence/schemas/ohlcv_schema.py` | Replaced by domain entity methods |

## Implementation Steps

### 1. Migrate `Bar` entity (dataclass → Pydantic)

```python
# src/domain/ohlcv/entities.py
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr
from src.common.uuid import UUID, generate_id

def _utc_now() -> datetime:
    return datetime.now(UTC)

class Bar(BaseModel):
    """OHLCV price bar with identity and MongoDB persistence."""
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(default_factory=generate_id)
    symbol: str = ""
    exchange: str = ""
    interval: Interval | None = None
    datetime: datetime | None = None
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0
    tick_count: int = 0
    created_at: datetime = Field(default_factory=_utc_now)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Bar):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    @property
    def is_complete(self) -> bool:
        return self.tick_count > 0

    def to_mongo(self) -> dict[str, Any]:
        """Serialize to MongoDB document."""
        return {
            "_id": str(self.id),
            "symbol": self.symbol,
            "exchange": self.exchange,
            "interval": self.interval.value if self.interval else None,
            "datetime": self.datetime,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "tick_count": self.tick_count,
            "created_at": self.created_at,
        }

    @classmethod
    def from_mongo(cls, doc: dict[str, Any]) -> "Bar":
        """Reconstruct from MongoDB document."""
        raw_id = doc.get("_id", "")
        interval_val = doc.get("interval")
        if isinstance(interval_val, str):
            interval_val = Interval(interval_val)
        return cls(
            id=UUID(str(raw_id)) if raw_id else generate_id(),
            symbol=doc.get("symbol", ""),
            exchange=doc.get("exchange", ""),
            interval=interval_val,
            datetime=doc.get("datetime"),
            open=doc.get("open", 0.0),
            high=doc.get("high", 0.0),
            low=doc.get("low", 0.0),
            close=doc.get("close", 0.0),
            volume=doc.get("volume", 0.0),
            tick_count=doc.get("tick_count", 0),
            created_at=doc.get("created_at", _utc_now()),
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for API serialization."""
        return {
            "id": str(self.id),
            "symbol": self.symbol,
            "exchange": self.exchange,
            "interval": self.interval.value if self.interval else None,
            "datetime": self.datetime.isoformat() if self.datetime else None,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "tick_count": self.tick_count,
        }
```

### 2. Migrate `SyncStatus` entity

```python
class SyncStatus(BaseModel):
    """Tracks data sync status for symbol/exchange/interval."""
    symbol: str = ""
    exchange: str = ""
    interval: str = ""
    status: str = "pending"
    last_sync_at: datetime | None = None
    last_bar_at: datetime | None = None
    bar_count: int = 0
    error_message: str | None = None

    @classmethod
    def from_mongo(cls, doc: dict[str, Any]) -> "SyncStatus":
        doc.pop("_id", None)
        return cls(**doc)
```

### 3. Update `OHLCVRepository`

- Remove `from src.persistence.schemas.ohlcv_schema import OHLCV, OHLCVBase`
- `upsert_many(records: list[Bar])` — call `bar.to_mongo()` directly
- `upsert_bar(bar: Bar)` — call `bar.to_mongo()` directly
- Remove `_doc_to_bar()` helper → use `Bar.from_mongo(doc)`
- Add `$set updated_at` in upsert operations

### 4. Update `SyncStatusRepository`

- Remove `_doc_to_sync_status()` helper → use `SyncStatus.from_mongo(doc)`

### 5. Update handler + infrastructure

- `sync_one/handler.py`: replace `OHLCVBase(...)` with `Bar(...)` construction
- `tradingview/base.py` + `tradingview_client.py`: replace `OHLCVBase` with `Bar` in type hints and returns

### 6. Relocate `OHLCVResponse`

Move inline into `src/features/market_data/ohlcv/get_ohlcv/route.py` (only used there).

### 7. Delete `src/persistence/schemas/ohlcv_schema.py`

### 8. Compile check + test

```bash
ruff check src/ && pyright src/ && pytest
```

## Success Criteria

- [x] `Bar` is Pydantic BaseModel with `to_mongo()`/`from_mongo()`
- [x] `SyncStatus` is Pydantic BaseModel with `from_mongo()`
- [x] No imports from `src.persistence.schemas.ohlcv_schema` anywhere
- [x] `ohlcv_schema.py` deleted
- [x] All `_id` values are UUID7 strings for OHLCV docs
- [x] `created_at` set once at entity creation, `updated_at` set by repo
- [x] All tests pass
